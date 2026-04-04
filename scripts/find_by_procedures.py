# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "duckdb"]
# ///
"""
Stage 4: Find physicians who frequently perform piriformis-relevant procedures,
using CMS Medicare Provider Utilization and Payment Data via DuckDB.

When a CMS DuckDB database is available, procedure volume queries run in
milliseconds instead of scanning a ~300 MB CSV (~10M rows).

Reads:   data/physicians.json (optional, to flag published authors)
Outputs: data/procedure_physicians.json
         data/procedure_physicians.csv

Usage: uv run find_by_procedures.py [--state IL] [--city Chicago]
                                     [--min-score 10] [--top 500]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from cms_db import (
    TARGET_HCPCS,
    CmsDb,
    batch_nppes,
    is_relevant_cms_specialty,
    parse_nppes_result,
)

DATA_DIR = Path("data")


def load_published_npis() -> set[str]:
    """Load NPIs from the PubMed-derived physicians.json, if it exists."""
    path = DATA_DIR / "physicians.json"
    if not path.exists():
        return set()
    with open(path) as f:
        physicians = json.load(f)
    return {p["npi"] for p in physicians if p.get("npi")}


def run(
    state: str | None = None,
    city: str | None = None,
    published_npis: set[str] | None = None,
    min_score: float = 10.0,
    top: int = 500,
    cms_db: CmsDb | None = None,
) -> list[dict]:
    """Find physicians by CMS procedure volume. Returns enriched list."""
    DATA_DIR.mkdir(exist_ok=True)

    # Get or create CMS database
    if cms_db is None:
        cms_db = CmsDb.ensure()

    # Query procedure volume via DuckDB (replaces 10M-row CSV scan)
    print("\n=== Querying procedure volume (DuckDB) ===")
    providers = cms_db.procedure_volume(state=state, city=city)
    print(f"  Providers with relevant procedures: {len(providers):,}")

    # Filter and rank
    print("\n=== Filtering and ranking ===")
    ranked = sorted(providers.values(), key=lambda p: -p["total_weighted_score"])
    ranked = [p for p in ranked if p["total_weighted_score"] >= min_score]
    print(f"  Providers with score >= {min_score}: {len(ranked):,}")

    # Load published NPIs for cross-reference
    if published_npis is None:
        published_npis = load_published_npis()
    print(f"  Published author NPIs loaded: {len(published_npis)}")

    # Enrich top providers — only query NPPES for those missing city/state
    top_providers = ranked[:top]
    needs_nppes = [
        (i, p) for i, p in enumerate(top_providers)
        if not (p.get("city") and p.get("state"))
    ]

    if needs_nppes:
        print(f"\n=== Enriching {len(needs_nppes)} providers via NPPES (concurrent) ===")
        param_list = [
            {"number": p["npi"], "enumeration_type": "NPI-1"}
            for _, p in needs_nppes
        ]
        responses = batch_nppes(param_list)

        for (idx, _), resp in zip(needs_nppes, responses):
            if resp.get("error") or not resp.get("results"):
                continue
            parsed = parse_nppes_result(resp["results"][0])
            p = top_providers[idx]
            addr = parsed.get("practice_address") or {}
            p["first_name"] = parsed.get("first_name") or p["first_name"]
            p["last_name"] = parsed.get("last_name") or p["last_name"]
            p["credential"] = parsed.get("credential") or p["credential"]
            p["specialty"] = parsed.get("specialty") or p["specialty"]
            p["city"] = addr.get("city") or p["city"]
            p["state"] = addr.get("state") or p["state"]
            p["zip"] = addr.get("postal_code") or p["zip"]

        print(f"  Done enriching {len(needs_nppes)} providers")
    else:
        print(f"\n  All top {len(top_providers)} providers have location data, "
              f"no NPPES enrichment needed")

    # Build output records
    enriched = []
    for p in top_providers:
        also_published = p["npi"] in published_npis
        record = {
            "npi": p["npi"],
            "last_name": p["last_name"],
            "first_name": p["first_name"],
            "credential": p["credential"],
            "specialty": p["specialty"],
            "city": p["city"],
            "state": p["state"],
            "zip": p["zip"],
            "address": None,
            "is_relevant_specialty": is_relevant_cms_specialty(p.get("specialty", "")),
            "weighted_score": p["total_weighted_score"],
            "procedure_volume": p["codes"],
            "also_published": also_published,
        }
        enriched.append(record)

    # Summary
    print(f"\n=== Top 20 by weighted score ===")
    print(f"{'Score':>8}  {'NPI':>12}  {'Name':<30}  {'Specialty':<35}  {'Location'}")
    print("-" * 120)
    for rec in enriched[:20]:
        name = f"{rec.get('first_name', '')} {rec.get('last_name', '')}".strip()
        loc = f"{rec.get('city', '')}, {rec.get('state', '')}".strip(", ")
        spec = (rec.get("specialty") or "")[:35]
        pub_flag = " *" if rec["also_published"] else ""
        print(
            f"  {rec['weighted_score']:>6.0f}  {rec['npi']:>12}  "
            f"{name:<30}  {spec:<35}  {loc}{pub_flag}"
        )

    published_also = sum(1 for r in enriched if r["also_published"])
    print(f"\n* = also in published-author set ({published_also} total)")
    print(f"Min score filter: {min_score}")
    print(f"State filter: {state or 'none'}")
    print(f"City filter: {city or 'none'}")

    return enriched


def main():
    parser = argparse.ArgumentParser(
        description="Find physicians by procedure volume (DuckDB-backed)"
    )
    parser.add_argument(
        "--min-score", type=float, default=10.0,
        help="Minimum weighted score (default: 10)",
    )
    parser.add_argument("--state", help="Filter to state (e.g., IL)")
    parser.add_argument("--city", help="Filter to city (e.g., Chicago)")
    parser.add_argument(
        "--top", type=int, default=500,
        help="Max providers to return (default: 500)",
    )
    parser.add_argument(
        "--refresh-cms", action="store_true",
        help="Force re-download and re-import of CMS data",
    )
    parser.add_argument(
        "--url",
        help="Manual override: direct CSV download URL for CMS file",
    )
    args = parser.parse_args()

    cms_db = CmsDb.ensure(refresh=args.refresh_cms, csv_url=args.url)

    try:
        enriched = run(
            state=args.state,
            city=args.city,
            min_score=args.min_score,
            top=args.top,
            cms_db=cms_db,
        )
    except RuntimeError:
        sys.exit(1)
    finally:
        cms_db.close()

    # Output
    json_path = DATA_DIR / "procedure_physicians.json"
    csv_path = DATA_DIR / "procedure_physicians.csv"

    with open(json_path, "w") as f:
        json.dump(enriched, f, indent=2)
    print(f"\nSaved {json_path}")

    fieldnames = [
        "npi", "last_name", "first_name", "credential", "specialty",
        "city", "state", "zip", "weighted_score", "also_published",
        "is_relevant_specialty",
    ] + sorted(TARGET_HCPCS.keys())

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rec in enriched:
            row = {k: v for k, v in rec.items() if k != "procedure_volume"}
            for code in TARGET_HCPCS:
                row[code] = rec["procedure_volume"].get(code, {}).get("services", 0)
            writer.writerow(row)
    print(f"Saved {csv_path}")


if __name__ == "__main__":
    main()
