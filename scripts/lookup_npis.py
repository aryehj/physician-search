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


import re as _re

# State abbreviation → full name (for matching both forms in affiliations)
_STATE_ABBREVS = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}
_FULL_TO_ABBREV = {v.lower(): k for k, v in _STATE_ABBREVS.items()}


def _extract_us_states(affiliations: list[str]) -> set[str]:
    """Extract US state abbreviations mentioned in affiliation strings.

    Returns a set of 2-letter state codes (e.g. {"IL", "TX"}).
    """
    states = set()
    for aff in affiliations:
        # Match ", XX " or ", XX," or ", XX." where XX is a state abbrev
        for m in _re.finditer(r",\s+([A-Z]{2})[\s,.\d]", aff):
            code = m.group(1)
            if code in _STATE_ABBREVS:
                states.add(code)
        # Match full state names (e.g. "Oklahoma", "Illinois")
        aff_lower = aff.lower()
        for full_name, code in _FULL_TO_ABBREV.items():
            if full_name in aff_lower:
                states.add(code)
    return states


def has_us_affiliation(author: dict) -> bool:
    """Heuristic: does the author appear to be US-based?"""
    us_markers = [
        "USA", "United States", ", US", "U.S.A",
    ]
    for aff in author.get("affiliations", []):
        if any(marker in aff for marker in us_markers):
            return True
    # Also check if any state abbreviations were found
    if _extract_us_states(author.get("affiliations", [])):
        return True
    return False


def _first_name_compatible(author_first: str, provider_first: str) -> bool:
    """Check if author first name is compatible with provider first name.

    Handles initials, abbreviated names, and multi-word first names.
    Returns True if they plausibly refer to the same person.
    """
    af = author_first.strip().lower()
    pf = provider_first.strip().lower()
    if not af or not pf:
        return True  # can't tell, be permissive

    # Split on spaces/hyphens to get name tokens
    a_parts = _re.split(r"[\s\-]+", af)
    p_parts = _re.split(r"[\s\-]+", pf)

    a1 = a_parts[0]
    p1 = p_parts[0]

    # Exact match on first token
    if a1 == p1:
        return True
    # One is an initial of the other (e.g. "N" vs "Nikhil")
    if len(a1) == 1 or len(p1) == 1:
        return a1[0] == p1[0]
    # One starts with the other (e.g. "Dan" vs "Daniel")
    if a1.startswith(p1) or p1.startswith(a1):
        return True

    return False


def _affiliation_matches_location(
    affiliations: list[str], state: str | None, city: str | None
) -> str:
    """Score how well author affiliations match a provider's practice location.

    Returns: "state_match", "no_conflict", or "state_mismatch".
    """
    if not affiliations or not state:
        return "no_conflict"

    author_states = _extract_us_states(affiliations)
    if not author_states:
        # Author has affiliations but no detectable US state — likely non-US
        # Check if affiliations look non-US
        non_us_markers = [
            "Korea", "Japan", "China", "Taiwan", "India", "Bangladesh",
            "Turkey", "France", "Germany", "UK", "United Kingdom", "Italy",
            "Spain", "Brazil", "Canada", "Australia", "Netherlands",
            "Switzerland", "Sweden", "Iran", "Egypt", "Pakistan", "Thailand",
            "Indonesia", "Malaysia", "Singapore", "Mexico", "Colombia",
            "Argentina", "Israel", "Saudi Arabia", "Greece", "Poland",
            "Czech", "Austria", "Belgium", "Portugal", "Denmark", "Norway",
            "Finland", "Ireland", "Romania", "Hungary",
        ]
        for aff in affiliations:
            if any(marker in aff for marker in non_us_markers):
                return "state_mismatch"
        return "no_conflict"

    if state in author_states:
        return "state_match"
    else:
        return "state_mismatch"


def match_author_to_npi(author: dict, npi_results: list[dict]) -> list[dict]:
    """Given an author and their NPI lookup results, return the best matches.

    Applies three filters in order:
    1. First-name compatibility (reject clearly different first names)
    2. Affiliation-based geographic validation
    3. Prefer relevant specialties
    """
    affiliations = author.get("affiliations", [])
    author_first = author.get("fore_name", "")

    # Filter by first-name compatibility
    name_ok = [
        r for r in npi_results
        if _first_name_compatible(author_first, r.get("first_name", ""))
    ]
    if not name_ok:
        name_ok = npi_results  # fall back if nothing matches

    # Score by affiliation geography
    def _geo_score(r):
        addr = r.get("practice_address") or {}
        state = addr.get("state") if isinstance(addr, dict) else None
        city = addr.get("city") if isinstance(addr, dict) else None
        match = _affiliation_matches_location(affiliations, state, city)
        return {"state_match": 2, "no_conflict": 1, "state_mismatch": 0}[match]

    # Separate into geo-validated vs not
    geo_good = [r for r in name_ok if _geo_score(r) >= 1]
    geo_matched = [r for r in name_ok if _geo_score(r) == 2]

    # Use geo-matched if available, otherwise geo-good, otherwise all
    pool = geo_matched or geo_good or name_ok

    # Prefer relevant specialties within the pool
    relevant = [r for r in pool if r.get("is_relevant_specialty")]
    return relevant if relevant else pool


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
        cms_geo_filtered = 0
        cms_name_filtered = 0
        for author in candidates:
            results = cms_db.lookup_by_name(author["fore_name"], author["last_name"])
            if not results:
                nppes_needed.append(author)
                continue

            author_first = author.get("fore_name", "")
            affiliations = author.get("affiliations", [])

            # Filter by first-name compatibility
            name_ok = [
                r for r in results
                if _first_name_compatible(author_first, r.get("first_name", ""))
            ]
            if len(name_ok) < len(results):
                cms_name_filtered += len(results) - len(name_ok)
            if not name_ok:
                nppes_needed.append(author)
                continue

            # Filter by affiliation geography
            def _cms_geo(r):
                return _affiliation_matches_location(
                    affiliations, r.get("state"), r.get("city"),
                )

            geo_good = [r for r in name_ok if _cms_geo(r) != "state_mismatch"]
            geo_matched = [r for r in name_ok if _cms_geo(r) == "state_match"]
            pool = geo_matched or geo_good or name_ok

            if len(pool) < len(name_ok):
                cms_geo_filtered += len(name_ok) - len(pool)

            # Prefer relevant specialties
            relevant = [r for r in pool if is_relevant_cms_specialty(r["specialty"])]
            matches = relevant if relevant else pool

            if not matches:
                nppes_needed.append(author)
                continue

            cms_hits += 1
            for m in matches:
                is_rel = is_relevant_cms_specialty(m.get("specialty", ""))
                city = m.get("city")
                state = m.get("state")
                zip_code = m.get("zip", "")
                geo = _cms_geo(m)
                address = (
                    f"{city}, {state} {zip_code}" if city and state else None
                )
                # Build match quality string
                if is_rel and geo == "state_match":
                    quality = "affiliation_verified"
                elif is_rel:
                    quality = "relevant_specialty"
                elif geo == "state_match":
                    quality = "state_match"
                else:
                    quality = "name_only"
                physicians.append(_build_physician_record(
                    author,
                    npi=m["npi"],
                    credential=m.get("credential"),
                    specialty=m.get("specialty"),
                    city=city,
                    state=state,
                    address=address,
                    match_quality=quality,
                ))

        print(f"  CMS matches: {cms_hits}/{len(candidates)}")
        if cms_name_filtered:
            print(f"  Filtered out (first-name mismatch): {cms_name_filtered}")
        if cms_geo_filtered:
            print(f"  Filtered out (affiliation/geo mismatch): {cms_geo_filtered}")
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
                state = addr.get("state") if isinstance(addr, dict) else None
                city = addr.get("city") if isinstance(addr, dict) else None
                geo = _affiliation_matches_location(
                    author.get("affiliations", []), state, city,
                )
                is_rel = m.get("is_relevant_specialty", False)
                if is_rel and geo == "state_match":
                    quality = "affiliation_verified"
                elif is_rel:
                    quality = "relevant_specialty"
                elif geo == "state_match":
                    quality = "state_match"
                else:
                    quality = "name_only"
                physicians.append(_build_physician_record(
                    author,
                    npi=m["npi"],
                    credential=m["credential"],
                    specialty=primary_spec,
                    city=city,
                    state=state,
                    address=(
                        f"{addr.get('address_1', '')}, {city}, "
                        f"{state} {addr.get('postal_code', '')}"
                        if city else None
                    ),
                    match_quality=quality,
                ))

    # --- Summary ---
    verified_count = sum(
        1 for p in physicians if p["npi_match_quality"] == "affiliation_verified"
    )
    relevant_count = sum(
        1 for p in physicians if p["npi_match_quality"] == "relevant_specialty"
    )
    state_match_count = sum(
        1 for p in physicians if p["npi_match_quality"] == "state_match"
    )
    name_only_count = sum(
        1 for p in physicians if p["npi_match_quality"] == "name_only"
    )
    no_match_count = sum(
        1 for p in physicians if p["npi_match_quality"] == "none"
    )

    print(f"\n=== Summary ===")
    print(f"  Authors queried:          {len(candidates)}")
    print(f"  Affiliation verified:      {verified_count}")
    print(f"  Relevant specialty match:  {relevant_count}")
    print(f"  State match (other spec):  {state_match_count}")
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
