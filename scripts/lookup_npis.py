# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "duckdb"]
# ///
"""
Stage 2: Look up NPI numbers for authors found in Stage 1.

Reads:   data/authors.json  (from fetch_authors.py)
Outputs: data/physicians.csv (authors enriched with NPI + practice info)
         data/physicians.json (same, as JSON for programmatic use)

When a CMS DuckDB database is available (from cms_db.py), uses it for
fast name→NPI matching and only falls back to NPPES API for misses.
All NPPES queries run concurrently (~10x faster than serial).

Usage: uv run lookup_npis.py [--all]
"""

import csv
import json
import sys
from pathlib import Path

from cms_db import (
    batch_nppes,
    is_relevant_cms_specialty,
    parse_nppes_result,
)

DATA_DIR = Path("data")


def has_us_affiliation(author: dict) -> bool:
    """Heuristic: does the author appear to be US-based?"""
    us_markers = [
        "USA", "United States", ", US", "U.S.A",
        ", AL ", ", AK ", ", AZ ", ", AR ", ", CA ", ", CO ", ", CT ", ", DE ",
        ", FL ", ", GA ", ", HI ", ", ID ", ", IL ", ", IN ", ", IA ", ", KS ",
        ", KY ", ", LA ", ", ME ", ", MD ", ", MA ", ", MI ", ", MN ", ", MS ",
        ", MO ", ", MT ", ", NE ", ", NV ", ", NH ", ", NJ ", ", NM ", ", NY ",
        ", NC ", ", ND ", ", OH ", ", OK ", ", OR ", ", PA ", ", RI ", ", SC ",
        ", SD ", ", TN ", ", TX ", ", UT ", ", VT ", ", VA ", ", WA ", ", WV ",
        ", WI ", ", WY ",
    ]
    for aff in author.get("affiliations", []):
        if any(marker in aff for marker in us_markers):
            return True
    return False


def match_author_to_npi(author: dict, npi_results: list[dict]) -> list[dict]:
    """Given an author and their NPI lookup results, return the best matches.
    Prefer relevant specialties."""
    relevant = [r for r in npi_results if r["is_relevant_specialty"]]
    return relevant if relevant else npi_results


def _build_physician_record(
    author: dict,
    npi: str | None,
    credential: str | None,
    specialty: str | None,
    city: str | None,
    state: str | None,
    address: str | None,
    match_quality: str,
) -> dict:
    """Build a physician record combining author metadata with NPI data."""
    return {
        "last_name": author["last_name"],
        "fore_name": author["fore_name"],
        "article_count": author["article_count"],
        "pmids": author["pmids"],
        "affiliations": author["affiliations"],
        "npi": npi,
        "credential": credential,
        "specialty": specialty,
        "practice_city": city,
        "practice_state": state,
        "practice_address": address,
        "npi_match_quality": match_quality,
    }


def run(authors: list[dict], query_all: bool = False, cms_db=None) -> list[dict]:
    """Look up NPI numbers for authors. Returns list of physician dicts.

    Args:
        authors: Author records from fetch_authors.
        query_all: If True, query all authors regardless of affiliation.
        cms_db: Optional CmsDb instance for fast name→NPI matching.
    """
    # Filter to queryable authors
    if query_all:
        candidates = authors
        print("Querying ALL authors (--all flag)")
    else:
        candidates = [
            a for a in authors if has_us_affiliation(a) or not a["affiliations"]
        ]
        print(
            f"Filtered to {len(candidates)} authors with US or unknown affiliation"
        )
        print("(pass --all to query all authors)")

    physicians = []
    nppes_needed = []  # authors that need NPPES fallback

    # --- Phase 1: CMS DB lookup (instant, if available) ---
    if cms_db:
        print(f"\n=== CMS database lookup for {len(candidates)} authors ===")
        cms_hits = 0
        for author in candidates:
            results = cms_db.lookup_by_name(author["fore_name"], author["last_name"])
            if not results:
                nppes_needed.append(author)
                continue

            cms_hits += 1
            relevant = [r for r in results if is_relevant_cms_specialty(r["specialty"])]
            matches = relevant if relevant else results

            for m in matches:
                is_rel = is_relevant_cms_specialty(m.get("specialty", ""))
                city = m.get("city")
                state = m.get("state")
                zip_code = m.get("zip", "")
                address = (
                    f"{city}, {state} {zip_code}" if city and state else None
                )
                physicians.append(_build_physician_record(
                    author,
                    npi=m["npi"],
                    credential=m.get("credential"),
                    specialty=m.get("specialty"),
                    city=city,
                    state=state,
                    address=address,
                    match_quality="relevant_specialty" if is_rel else "name_only",
                ))

        print(f"  CMS matches: {cms_hits}/{len(candidates)}")
        print(f"  NPPES fallback needed: {len(nppes_needed)}")
    else:
        nppes_needed = list(candidates)

    # --- Phase 2: Concurrent NPPES queries for misses ---
    if nppes_needed:
        print(
            f"\n=== Querying NPPES for {len(nppes_needed)} authors "
            f"(concurrent) ==="
        )

        # Build query params
        param_list = []
        valid_indices = []
        for i, author in enumerate(nppes_needed):
            first = author["fore_name"].split()[0] if author["fore_name"] else ""
            if first and author["last_name"]:
                param_list.append({
                    "first_name": first,
                    "last_name": author["last_name"],
                    "enumeration_type": "NPI-1",
                    "limit": 20,
                })
                valid_indices.append(i)

        # Batch query
        responses = batch_nppes(param_list)
        errors = sum(1 for r in responses if r.get("error"))
        print(f"  Responses: {len(responses) - errors} OK, {errors} errors")

        # Map responses back to authors
        response_by_idx = dict(zip(valid_indices, responses))

        for i, author in enumerate(nppes_needed):
            resp = response_by_idx.get(i)
            name = f"{author['fore_name']} {author['last_name']}"

            if not resp or resp.get("error") or resp.get("result_count", 0) == 0:
                physicians.append(_build_physician_record(
                    author, npi=None, credential=None, specialty=None,
                    city=None, state=None, address=None,
                    match_quality="none",
                ))
                continue

            npi_results = [
                parse_nppes_result(r) for r in resp.get("results", [])
            ]
            matches = match_author_to_npi(author, npi_results)

            for m in matches:
                primary_spec = next(
                    (s["description"] for s in m["specialties"] if s["primary"]),
                    m["specialties"][0]["description"] if m["specialties"] else None,
                )
                addr = m["practice_address"] or {}
                physicians.append(_build_physician_record(
                    author,
                    npi=m["npi"],
                    credential=m["credential"],
                    specialty=primary_spec,
                    city=addr.get("city"),
                    state=addr.get("state"),
                    address=(
                        f"{addr.get('address_1', '')}, {addr.get('city', '')}, "
                        f"{addr.get('state', '')} {addr.get('postal_code', '')}"
                        if addr.get("city") else None
                    ),
                    match_quality=(
                        "relevant_specialty"
                        if m["is_relevant_specialty"]
                        else "name_only"
                    ),
                ))

    # --- Summary ---
    relevant_count = sum(
        1 for p in physicians if p["npi_match_quality"] == "relevant_specialty"
    )
    name_only_count = sum(
        1 for p in physicians if p["npi_match_quality"] == "name_only"
    )
    no_match_count = sum(
        1 for p in physicians if p["npi_match_quality"] == "none"
    )

    print(f"\n=== Summary ===")
    print(f"  Authors queried:          {len(candidates)}")
    print(f"  Relevant specialty match:  {relevant_count}")
    print(f"  Name match (other spec):   {name_only_count}")
    print(f"  No NPI match:             {no_match_count}")
    print(f"  Total physician records:   {len(physicians)}")

    return physicians


def main():
    query_all = "--all" in sys.argv

    authors_path = DATA_DIR / "authors.json"
    if not authors_path.exists():
        print("Error: data/authors.json not found. Run fetch_authors.py first.")
        sys.exit(1)

    with open(authors_path) as f:
        authors = json.load(f)
    print(f"Loaded {len(authors)} authors from {authors_path}")

    # Try to use CMS DB if available
    cms_db = None
    try:
        from cms_db import CmsDb, DB_PATH
        if DB_PATH.exists():
            cms_db = CmsDb.ensure()
    except Exception as e:
        print(f"CMS database not available ({e}), using NPPES only")

    physicians = run(authors, query_all, cms_db=cms_db)

    if cms_db:
        cms_db.close()

    # Save JSON
    json_path = DATA_DIR / "physicians.json"
    with open(json_path, "w") as f:
        json.dump(physicians, f, indent=2)
    print(f"\nSaved {json_path}")

    # Save CSV (flattened)
    csv_path = DATA_DIR / "physicians.csv"
    fieldnames = [
        "last_name", "fore_name", "article_count", "npi", "credential",
        "specialty", "practice_city", "practice_state", "practice_address",
        "npi_match_quality", "affiliations",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for p in physicians:
            row = {**p, "affiliations": "; ".join(p["affiliations"])}
            writer.writerow(row)
    print(f"Saved {csv_path}")

    # Print relevant-specialty matches
    relevant = [
        p for p in physicians if p["npi_match_quality"] == "relevant_specialty"
    ]
    if relevant:
        print(f"\n=== Physicians with relevant specialties ({len(relevant)}) ===")
        for p in sorted(relevant, key=lambda x: -x["article_count"]):
            loc = (
                f"{p['practice_city']}, {p['practice_state']}"
                if p["practice_city"] else "?"
            )
            print(
                f"  {p['fore_name']} {p['last_name']}, {p['credential'] or '?'} "
                f"— {p['specialty']} — {loc} "
                f"— {p['article_count']} pub(s) — NPI {p['npi']}"
            )


if __name__ == "__main__":
    main()
