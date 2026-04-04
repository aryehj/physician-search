# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "lxml", "python-dotenv"]
# ///

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from fetch_authors import run as fetch_authors_run
from lookup_npis import run as lookup_npis_run
from find_practice_colleagues import run as find_practice_colleagues_run
from find_by_procedures import run as find_by_procedures_run
from merge_and_rank import run as merge_and_rank_run
from merge_and_rank import compute_score, rank_sort_key
from check_anthem_network import run as check_anthem_network_run

DATA_DIR = Path("data")


def save_json(data: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Saved {path} ({len(data)} records)")


def main():
    parser = argparse.ArgumentParser(description="Run the full physician search pipeline.")
    parser.add_argument("--state", help="Filter by state (e.g. IL)")
    parser.add_argument("--city", help="Filter by city (e.g. Chicago)")
    parser.add_argument("--top", type=int, default=200, help="Top N to check against Anthem (default: 200)")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    # Stage 1: Fetch authors from PubMed
    print("\n" + "=" * 60)
    print("STAGE 1: Fetch authors from PubMed")
    print("=" * 60)
    articles, authors = fetch_authors_run()
    save_json(articles, DATA_DIR / "articles.json")
    save_json(authors, DATA_DIR / "authors.json")

    # Stage 2: Look up NPI numbers
    print("\n" + "=" * 60)
    print("STAGE 2: Look up NPI numbers")
    print("=" * 60)
    physicians = lookup_npis_run(authors)
    save_json(physicians, DATA_DIR / "physicians.json")

    # Stage 3: Find practice colleagues
    print("\n" + "=" * 60)
    print("STAGE 3: Find practice colleagues")
    print("=" * 60)
    colleagues = find_practice_colleagues_run(physicians, state=args.state)
    save_json(colleagues, DATA_DIR / "practice_colleagues.json")

    # Stage 4: Find by procedure volume
    print("\n" + "=" * 60)
    print("STAGE 4: Find by procedure volume")
    print("=" * 60)
    published_npis = {p["npi"] for p in physicians if p.get("npi")}
    procedure_physicians = find_by_procedures_run(
        state=args.state,
        city=args.city,
        published_npis=published_npis,
    )
    save_json(procedure_physicians, DATA_DIR / "procedure_physicians.json")

    # Stage 5: Initial merge and rank (without Anthem data)
    print("\n" + "=" * 60)
    print("STAGE 5: Merge and rank (initial, without Anthem data)")
    print("=" * 60)
    ranked = merge_and_rank_run(
        physicians=physicians,
        in_network=[],
        procedures=procedure_physicians,
        colleagues=colleagues,
        state=args.state,
        city=args.city,
    )

    # Stage 6: Check top N against Anthem
    print("\n" + "=" * 60)
    print(f"STAGE 6: Check top {args.top} against Anthem network")
    print("=" * 60)
    top_n = ranked[:args.top]

    # TEMPORARY WORKAROUND (removed in Phase 3):
    # merge_and_rank output uses first_name, but check_anthem_network
    # expects fore_name for the FHIR name search.
    for rec in top_n:
        if "fore_name" not in rec:
            rec["fore_name"] = rec.get("first_name", "")

    in_network = check_anthem_network_run(top_n)
    save_json(in_network, DATA_DIR / "in_network_physicians.json")

    # Stage 7: Re-score with in-network data
    print("\n" + "=" * 60)
    print("STAGE 7: Re-score with in-network data")
    print("=" * 60)

    in_network_by_npi = {}
    for rec in in_network:
        npi = rec.get("npi")
        if npi:
            in_network_by_npi[str(npi)] = rec

    for rec in ranked:
        npi = str(rec.get("npi", ""))
        if npi in in_network_by_npi:
            anthem_data = in_network_by_npi[npi]
            rec["in_anthem_network"] = True
            rec["accepting_new_patients"] = anthem_data.get("accepting_new_patients", False)
            rec["anthem_networks"] = anthem_data.get("anthem_networks", [])
            rec["anthem_practitioner_id"] = anthem_data.get("anthem_practitioner_id", "")

    for rec in ranked:
        score, reasons = compute_score(rec)
        rec["score"] = round(score, 1)
        rec["reasons"] = reasons

    ranked.sort(key=rank_sort_key)

    for i, rec in enumerate(ranked, 1):
        rec["rank"] = i

    save_json(ranked, DATA_DIR / "ranked_physicians.json")

    # Summary
    in_network_count = sum(1 for r in ranked if r.get("in_anthem_network"))
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Total ranked physicians: {len(ranked)}")
    print(f"  In Anthem network: {in_network_count}")
    print()
    print("  Top 10:")
    for rec in ranked[:10]:
        network_tag = " [IN-NETWORK]" if rec.get("in_anthem_network") else ""
        print(f"    #{rec['rank']:<3} {rec['score']:<6} {rec.get('last_name', '')}, {rec.get('first_name', '')}{network_tag}")


if __name__ == "__main__":
    main()
