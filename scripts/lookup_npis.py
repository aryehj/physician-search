# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
Stage 2: Look up NPI numbers for authors found in Stage 1.

Reads:   data/authors.json  (from fetch_authors.py)
Outputs: data/physicians.csv (authors enriched with NPI + practice info)
         data/physicians.json (same, as JSON for programmatic use)

Filters to US-based physicians in relevant specialties.

Usage: uv run lookup_npis.py [--all]

By default, only queries authors with US affiliations or no affiliation
(since many PubMed records lack affiliation data). Pass --all to query
every author.
"""

import csv
import json
import sys
import time
from pathlib import Path

import httpx

NPPES_API = "https://npiregistry.cms.hhs.gov/api/"

# Taxonomy codes for specialties relevant to piriformis syndrome
RELEVANT_TAXONOMIES = {
    # Physical Medicine & Rehabilitation (Physiatry)
    "208100000X": "PM&R",
    "2081P2900X": "PM&R - Pain Medicine",
    "2081P0010X": "PM&R - Pediatric Rehab",
    "2081S0010X": "PM&R - Sports Medicine",
    # Pain Medicine
    "208VP0014X": "Pain Medicine",
    "2083P0500X": "Preventive Medicine - Pain Medicine",
    # Neurology
    "2084N0400X": "Neurology",
    "2084N0402X": "Neurology - Neuromuscular",
    "2084P0800X": "Neurology - Pain Medicine",
    "2084P0805X": "Neurology - Pediatric Neurology",
    # Orthopedic Surgery
    "207X00000X": "Orthopaedic Surgery",
    "207XS0114X": "Orthopaedic Surgery - Sports Medicine",
    "207XP3100X": "Orthopaedic Surgery - Pediatric",
    # Neurosurgery
    "207T00000X": "Neurological Surgery",
    # Anesthesiology (pain management)
    "207L00000X": "Anesthesiology",
    "207LP2900X": "Anesthesiology - Pain Medicine",
    # Sports Medicine
    "204C00000X": "Sports Medicine",
    # Radiology (interventional)
    "2085R0001X": "Radiology - Interventional",
    # General Surgery
    "208600000X": "Surgery",
}


def has_us_affiliation(author: dict) -> bool:
    """Heuristic: does the author appear to be US-based?"""
    us_markers = ["USA", "United States", ", US", "U.S.A", ", AL ", ", AK ",
                  ", AZ ", ", AR ", ", CA ", ", CO ", ", CT ", ", DE ", ", FL ",
                  ", GA ", ", HI ", ", ID ", ", IL ", ", IN ", ", IA ", ", KS ",
                  ", KY ", ", LA ", ", ME ", ", MD ", ", MA ", ", MI ", ", MN ",
                  ", MS ", ", MO ", ", MT ", ", NE ", ", NV ", ", NH ", ", NJ ",
                  ", NM ", ", NY ", ", NC ", ", ND ", ", OH ", ", OK ", ", OR ",
                  ", PA ", ", RI ", ", SC ", ", SD ", ", TN ", ", TX ", ", UT ",
                  ", VT ", ", VA ", ", WA ", ", WV ", ", WI ", ", WY "]
    for aff in author.get("affiliations", []):
        if any(marker in aff for marker in us_markers):
            return True
    return False


def query_npi(client: httpx.Client, first_name: str, last_name: str) -> list[dict]:
    """Query NPPES for a provider by name. Returns matching results."""
    # Use first name only (not middle initial) for broader matching
    first = first_name.split()[0] if first_name else ""
    if not first or not last_name:
        return []

    try:
        resp = client.get(
            NPPES_API,
            params={
                "version": "2.1",
                "first_name": first,
                "last_name": last_name,
                "enumeration_type": "NPI-1",  # individual providers only
                "limit": 20,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        print(f"    Error querying NPI for {first} {last_name}: {e}")
        return []

    if data.get("result_count", 0) == 0:
        return []

    results = []
    for r in data.get("results", []):
        # Extract taxonomy/specialty info
        taxonomies = r.get("taxonomies", [])
        specialties = []
        is_relevant = False

        for tax in taxonomies:
            code = tax.get("code", "")
            desc = tax.get("desc", "")
            primary = tax.get("primary", False)
            specialties.append(
                {"code": code, "description": desc, "primary": primary}
            )
            if code in RELEVANT_TAXONOMIES:
                is_relevant = True

        # Extract practice address
        addresses = r.get("addresses", [])
        practice_addr = None
        for addr in addresses:
            if addr.get("address_purpose") == "LOCATION":
                practice_addr = {
                    "address_1": addr.get("address_1", ""),
                    "address_2": addr.get("address_2", ""),
                    "city": addr.get("city", ""),
                    "state": addr.get("state", ""),
                    "postal_code": addr.get("postal_code", "")[:5],
                }
                break

        basic = r.get("basic", {})
        results.append(
            {
                "npi": r.get("number"),
                "first_name": basic.get("first_name", ""),
                "last_name": basic.get("last_name", ""),
                "credential": basic.get("credential", ""),
                "gender": basic.get("gender", ""),
                "specialties": specialties,
                "is_relevant_specialty": is_relevant,
                "practice_address": practice_addr,
                "enumeration_date": basic.get("enumeration_date", ""),
            }
        )

    return results


def match_author_to_npi(
    author: dict, npi_results: list[dict]
) -> list[dict]:
    """
    Given an author and their NPI lookup results, return the best matches.
    Prefer relevant specialties. If multiple matches, return all relevant ones.
    """
    relevant = [r for r in npi_results if r["is_relevant_specialty"]]
    if relevant:
        return relevant

    # If no relevant-specialty matches, return all (user can filter later)
    return npi_results


def run(authors: list[dict], query_all: bool = False) -> list[dict]:
    """Look up NPI numbers for authors. Returns list of physician dicts."""
    # Filter to queryable authors
    if query_all:
        candidates = authors
        print("Querying ALL authors (--all flag)")
    else:
        # Query US-affiliated authors + those with no affiliation (might be US)
        candidates = [
            a for a in authors if has_us_affiliation(a) or not a["affiliations"]
        ]
        print(
            f"Filtered to {len(candidates)} authors with US or unknown affiliation"
        )
        print("(pass --all to query all authors)")

    # Query NPPES for each candidate
    physicians = []  # final enriched records
    stats = {"queried": 0, "found": 0, "relevant": 0, "no_match": 0}

    with httpx.Client(timeout=15.0) as client:
        print(f"\n=== Querying NPPES for {len(candidates)} authors ===")

        for i, author in enumerate(candidates):
            name = f"{author['fore_name']} {author['last_name']}"
            print(f"  [{i + 1}/{len(candidates)}] {name}...", end=" ", flush=True)

            npi_results = query_npi(client, author["fore_name"], author["last_name"])
            stats["queried"] += 1

            if not npi_results:
                print("no NPI match")
                stats["no_match"] += 1
                # Still record the author even without NPI
                physicians.append(
                    {
                        "last_name": author["last_name"],
                        "fore_name": author["fore_name"],
                        "article_count": author["article_count"],
                        "pmids": author["pmids"],
                        "affiliations": author["affiliations"],
                        "npi": None,
                        "credential": None,
                        "specialty": None,
                        "practice_city": None,
                        "practice_state": None,
                        "practice_address": None,
                        "npi_match_quality": "none",
                    }
                )
                time.sleep(0.3)
                continue

            matches = match_author_to_npi(author, npi_results)
            relevant_matches = [m for m in matches if m["is_relevant_specialty"]]

            if relevant_matches:
                stats["relevant"] += 1
                label = f"{len(relevant_matches)} relevant match(es)"
            else:
                stats["found"] += 1
                label = f"{len(matches)} match(es), no relevant specialty"
            print(label)

            for m in matches:
                primary_spec = next(
                    (s["description"] for s in m["specialties"] if s["primary"]),
                    m["specialties"][0]["description"] if m["specialties"] else None,
                )
                addr = m["practice_address"] or {}
                physicians.append(
                    {
                        "last_name": author["last_name"],
                        "fore_name": author["fore_name"],
                        "article_count": author["article_count"],
                        "pmids": author["pmids"],
                        "affiliations": author["affiliations"],
                        "npi": m["npi"],
                        "credential": m["credential"],
                        "specialty": primary_spec,
                        "practice_city": addr.get("city"),
                        "practice_state": addr.get("state"),
                        "practice_address": (
                            f"{addr.get('address_1', '')}, {addr.get('city', '')}, "
                            f"{addr.get('state', '')} {addr.get('postal_code', '')}"
                            if addr.get("city")
                            else None
                        ),
                        "npi_match_quality": (
                            "relevant_specialty"
                            if m["is_relevant_specialty"]
                            else "name_only"
                        ),
                    }
                )

            time.sleep(0.3)  # rate limit

    # Summary
    print(f"\n=== Summary ===")
    print(f"  Authors queried:         {stats['queried']}")
    print(f"  Relevant specialty match: {stats['relevant']}")
    print(f"  Name match (other spec):  {stats['found']}")
    print(f"  No NPI match:            {stats['no_match']}")
    print(f"  Total physician records:  {len(physicians)}")

    return physicians


def main():
    query_all = "--all" in sys.argv

    data_dir = Path("data")
    authors_path = data_dir / "authors.json"

    if not authors_path.exists():
        print("Error: data/authors.json not found. Run fetch_authors.py first.")
        sys.exit(1)

    with open(authors_path) as f:
        authors = json.load(f)

    print(f"Loaded {len(authors)} authors from {authors_path}")

    physicians = run(authors, query_all)

    # Save JSON
    json_path = data_dir / "physicians.json"
    with open(json_path, "w") as f:
        json.dump(physicians, f, indent=2)
    print(f"\nSaved {json_path}")

    # Save CSV (flattened)
    csv_path = data_dir / "physicians.csv"
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

    # Print relevant-specialty matches as a quick reference
    relevant = [p for p in physicians if p["npi_match_quality"] == "relevant_specialty"]
    if relevant:
        print(f"\n=== Physicians with relevant specialties ({len(relevant)}) ===")
        for p in sorted(relevant, key=lambda x: -x["article_count"]):
            loc = f"{p['practice_city']}, {p['practice_state']}" if p["practice_city"] else "?"
            print(
                f"  {p['fore_name']} {p['last_name']}, {p['credential'] or '?'} "
                f"— {p['specialty']} — {loc} — {p['article_count']} pub(s) — NPI {p['npi']}"
            )


if __name__ == "__main__":
    main()
