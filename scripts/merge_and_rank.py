# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Merge three physician pipelines and produce a ranked call list.

Reads:   data/physicians.json           (Pipeline A — published authors)
         data/in_network_physicians.json (Pipeline A — Anthem in-network subset)
         data/procedure_physicians.json  (Pipeline B — CMS procedure volume)
         data/practice_colleagues.json   (Pipeline C — NPPES practice colleagues)
Outputs: data/ranked_physicians.json
         data/ranked_physicians.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

DATA_DIR = Path("data")

# Scoring weights
WEIGHTS = {
    "piriformis_27096_per_service": 0.6,   # per service, capped at 50 services
    "other_procedure_score_factor": 0.05,  # per weighted point, capped at 200
    "article_count_per_pub": 3.0,          # per publication, capped at 10
    "relevant_specialty": 10.0,
    "in_anthem_network": 15.0,
    "accepting_new_patients": 5.0,
    "colleague_high": 8.0,
    "colleague_hospital": 3.0,
    "colleague_zip_only": 1.0,
    "npi_match_relevant": 5.0,
}


def load_json(path: Path) -> list[dict]:
    """Load a JSON array file, returning empty list if missing."""
    if not path.exists():
        print(f"  (not found: {path})")
        return []
    with open(path) as f:
        data = json.load(f)
    print(f"  {path.name}: {len(data)} records")
    return data


def empty_record(npi: str) -> dict:
    return {
        "npi": npi,
        "first_name": "",
        "last_name": "",
        "credential": "",
        "specialty": "",
        "city": "",
        "state": "",
        "zip": "",
        "address": "",
        "is_relevant_specialty": False,
        "article_count": 0,
        "pmids": [],
        "npi_match_quality": None,
        "in_anthem_network": False,
        "accepting_new_patients": None,
        "anthem_networks": [],
        "weighted_procedure_score": 0.0,
        "piriformis_injection_services": 0,
        "procedure_volume": {},
        "colleague_of_npis": [],
        "colleague_match_type": None,
        "colleague_match_confidence": None,
        "sources": [],
    }


NPI_QUALITY_RANK = {"relevant_specialty": 0, "name_only": 1, "none": 2}


def build_merged_index(physicians, in_network, procedures, colleagues):
    """Full outer join on NPI across all pipelines."""
    index: dict[str, dict] = {}

    # Pass 1: Pipeline A
    for p in physicians:
        npi = p.get("npi")
        if not npi:
            continue
        quality = p.get("npi_match_quality", "none")
        if npi in index:
            existing_q = index[npi].get("npi_match_quality", "none")
            if NPI_QUALITY_RANK.get(quality, 2) < NPI_QUALITY_RANK.get(existing_q, 2):
                index[npi].update({
                    "first_name": p.get("fore_name", ""),
                    "last_name": p.get("last_name", ""),
                    "credential": p.get("credential", ""),
                    "specialty": p.get("specialty", ""),
                    "npi_match_quality": quality,
                })
            index[npi]["article_count"] = max(
                index[npi]["article_count"], p.get("article_count", 0)
            )
            index[npi]["pmids"] = list(set(
                index[npi].get("pmids", []) + p.get("pmids", [])
            ))
        else:
            rec = empty_record(npi)
            rec["first_name"] = p.get("fore_name", "")
            rec["last_name"] = p.get("last_name", "")
            rec["credential"] = p.get("credential", "")
            rec["specialty"] = p.get("specialty", "")
            rec["npi_match_quality"] = quality
            rec["article_count"] = p.get("article_count", 0)
            rec["pmids"] = p.get("pmids", [])
            rec["is_relevant_specialty"] = quality == "relevant_specialty"
            rec["sources"].append("publication")
            # Address from Pipeline A
            if p.get("practice_city"):
                rec["city"] = p["practice_city"]
                rec["state"] = p.get("practice_state", "")
                rec["address"] = p.get("practice_address", "")
            index[npi] = rec

    # Pass 2: In-network overlay
    for p in in_network:
        npi = p.get("npi")
        if not npi:
            continue
        if npi not in index:
            rec = empty_record(npi)
            rec["first_name"] = p.get("fore_name", "")
            rec["last_name"] = p.get("last_name", "")
            rec["credential"] = p.get("credential", "")
            rec["specialty"] = p.get("specialty", "")
            rec["npi_match_quality"] = p.get("npi_match_quality")
            rec["article_count"] = p.get("article_count", 0)
            rec["pmids"] = p.get("pmids", [])
            rec["is_relevant_specialty"] = (
                p.get("npi_match_quality") == "relevant_specialty"
            )
            rec["sources"].append("publication")
            if p.get("practice_city"):
                rec["city"] = p["practice_city"]
                rec["state"] = p.get("practice_state", "")
                rec["address"] = p.get("practice_address", "")
            index[npi] = rec
        rec = index[npi]
        rec["in_anthem_network"] = True
        rec["accepting_new_patients"] = p.get("accepting_new_patients")
        rec["anthem_networks"] = p.get("anthem_networks", [])

    # Pass 3: Pipeline B (procedure volume)
    for p in procedures:
        npi = p.get("npi")
        if not npi:
            continue
        if npi not in index:
            rec = empty_record(npi)
            rec["first_name"] = p.get("first_name", "")
            rec["last_name"] = p.get("last_name", "")
            rec["credential"] = p.get("credential", "")
            rec["specialty"] = p.get("specialty", "")
            index[npi] = rec
        rec = index[npi]
        rec["weighted_procedure_score"] = p.get("weighted_score", 0)
        rec["procedure_volume"] = p.get("procedure_volume", {})
        rec["piriformis_injection_services"] = (
            p.get("procedure_volume", {}).get("27096", {}).get("services", 0)
        )
        if p.get("is_relevant_specialty"):
            rec["is_relevant_specialty"] = True
        if "procedure" not in rec["sources"]:
            rec["sources"].append("procedure")
        # Backfill name/address
        if not rec["last_name"]:
            rec["first_name"] = p.get("first_name", "")
            rec["last_name"] = p.get("last_name", "")
            rec["credential"] = p.get("credential", "")
            rec["specialty"] = p.get("specialty", "")
        if not rec["city"]:
            rec["city"] = p.get("city", "")
            rec["state"] = p.get("state", "")
            rec["zip"] = p.get("zip", "")
            rec["address"] = p.get("address", "")

    # Pass 4: Pipeline C (practice colleagues)
    for p in colleagues:
        npi = p.get("npi")
        if not npi:
            continue
        if npi not in index:
            rec = empty_record(npi)
            rec["first_name"] = p.get("first_name", "")
            rec["last_name"] = p.get("last_name", "")
            rec["credential"] = p.get("credential", "")
            rec["specialty"] = p.get("specialty", "")
            rec["is_relevant_specialty"] = True  # Pipeline C only finds relevant specialties
            index[npi] = rec
        rec = index[npi]
        rec["colleague_of_npis"] = p.get("colleague_of", [])
        rec["colleague_match_type"] = p.get("match_type")
        rec["colleague_match_confidence"] = p.get("match_confidence")
        if not rec["is_relevant_specialty"]:
            rec["is_relevant_specialty"] = True
        if "colleague" not in rec["sources"]:
            rec["sources"].append("colleague")
        # Backfill
        if not rec["last_name"]:
            rec["first_name"] = p.get("first_name", "")
            rec["last_name"] = p.get("last_name", "")
            rec["credential"] = p.get("credential", "")
            rec["specialty"] = p.get("specialty", "")
        if not rec["city"]:
            rec["city"] = p.get("practice_city", "")
            rec["state"] = p.get("practice_state", "")
            rec["zip"] = p.get("practice_zip", "")
            rec["address"] = p.get("practice_address_1", "")

    return index


def compute_score(rec: dict) -> tuple[float, list[str]]:
    """Compute composite score and human-readable reasons."""
    score = 0.0
    reasons = []

    # 27096 piriformis injection services
    svc_27096 = rec.get("piriformis_injection_services", 0)
    if svc_27096 > 0:
        pts = min(svc_27096, 50) * WEIGHTS["piriformis_27096_per_service"]
        score += pts
        reasons.append(f"{svc_27096} piriformis injections (27096)")

    # Other procedure volume (subtract 27096 contribution from weighted score)
    total_proc = rec.get("weighted_procedure_score", 0)
    other_proc = total_proc - (svc_27096 * 10)  # 27096 has weight 10
    if other_proc > 0:
        pts = min(other_proc, 200) * WEIGHTS["other_procedure_score_factor"]
        score += pts
        reasons.append(f"procedure score {total_proc:.0f}")

    # Publications
    arts = rec.get("article_count", 0)
    if arts > 0:
        pts = min(arts, 10) * WEIGHTS["article_count_per_pub"]
        score += pts
        reasons.append(f"{arts} publication(s)")

    # Relevant specialty
    if rec.get("is_relevant_specialty"):
        score += WEIGHTS["relevant_specialty"]
        reasons.append("relevant specialty")

    # Anthem network
    if rec.get("in_anthem_network"):
        score += WEIGHTS["in_anthem_network"]
        reasons.append("in Anthem network")

    # Accepting new patients
    if rec.get("accepting_new_patients"):
        score += WEIGHTS["accepting_new_patients"]
        reasons.append("accepting new patients")

    # Colleague signals
    conf = rec.get("colleague_match_confidence")
    if conf == "high":
        score += WEIGHTS["colleague_high"]
        reasons.append("colleague of expert (same address)")
    elif conf == "low_hospital_campus":
        score += WEIGHTS["colleague_hospital"]
        reasons.append("colleague (hospital campus)")
    elif conf == "low_zip_only":
        score += WEIGHTS["colleague_zip_only"]
        reasons.append("same zip as expert")

    # NPI match quality bonus
    if rec.get("npi_match_quality") == "relevant_specialty":
        score += WEIGHTS["npi_match_relevant"]
        reasons.append("NPI confirmed relevant specialty")

    return score, reasons


def apply_filters(records: list[dict], args) -> list[dict]:
    """Apply geographic and threshold filters."""
    filtered = records

    if args.state:
        state = args.state.upper()
        filtered = [r for r in filtered if r.get("state", "").upper() == state]

    if args.city:
        city = args.city.lower()
        filtered = [r for r in filtered if r.get("city", "").lower() == city]

    if args.in_network_only:
        filtered = [r for r in filtered if r.get("in_anthem_network")]

    if args.exclude_zip_only:
        filtered = [
            r for r in filtered
            if r.get("colleague_match_confidence") != "low_zip_only"
            or len(r.get("sources", [])) > 1  # keep if also from another pipeline
            or r.get("colleague_match_confidence") is None
        ]

    if args.min_score > 0:
        filtered = [r for r in filtered if r["score"] >= args.min_score]

    if args.top:
        filtered = filtered[: args.top]

    return filtered


def print_summary(records: list[dict], max_rows: int = 30):
    """Print ranked table to console."""
    show = records[:max_rows]
    if not show:
        print("\nNo records to display.")
        return

    print(f"\n{'Rank':>4}  {'Score':>5}  {'Name':<28}  {'Specialty':<22}  {'Location':<18}  Reasons")
    print("-" * 120)
    for r in show:
        name = f"{r['last_name']}, {r['first_name']}"
        if len(name) > 26:
            name = name[:25] + "\u2026"
        loc = f"{r['city']}, {r['state']}" if r['city'] else r['state'] or "?"
        if len(loc) > 16:
            loc = loc[:15] + "\u2026"
        spec = r.get("specialty", "")
        if len(spec) > 20:
            spec = spec[:19] + "\u2026"
        top_reasons = "; ".join(r["reasons"][:3])
        if len(r["reasons"]) > 3:
            top_reasons += f" (+{len(r['reasons']) - 3} more)"
        print(f"{r['rank']:>4}  {r['score']:>5.1f}  {name:<28}  {spec:<22}  {loc:<18}  {top_reasons}")

    if len(records) > max_rows:
        print(f"\n  ... and {len(records) - max_rows} more (see ranked_physicians.json)")


def main():
    parser = argparse.ArgumentParser(
        description="Merge physician pipelines and produce a ranked call list."
    )
    parser.add_argument("--state", help="Filter to providers in this state")
    parser.add_argument("--city", help="Filter to providers in this city")
    parser.add_argument(
        "--min-score", type=float, default=1.0,
        help="Minimum composite score to include (default: 1.0)",
    )
    parser.add_argument(
        "--top", type=int, default=None,
        help="Max records in output",
    )
    parser.add_argument(
        "--in-network-only", action="store_true",
        help="Only include providers found in Anthem directory",
    )
    parser.add_argument(
        "--exclude-zip-only", action="store_true",
        help="Exclude low-confidence zip-only colleague matches",
    )
    args = parser.parse_args()

    print("Loading datasets...")
    physicians = load_json(DATA_DIR / "physicians.json")
    in_network = load_json(DATA_DIR / "in_network_physicians.json")
    procedures = load_json(DATA_DIR / "procedure_physicians.json")
    colleagues = load_json(DATA_DIR / "practice_colleagues.json")

    print("\nMerging on NPI...")
    index = build_merged_index(physicians, in_network, procedures, colleagues)
    print(f"  {len(index)} unique NPIs")

    # Score all records
    for rec in index.values():
        score, reasons = compute_score(rec)
        rec["score"] = round(score, 1)
        rec["reasons"] = reasons

    # Sort by score descending, then tie-breakers
    records = sorted(index.values(), key=lambda r: (
        -r["score"],
        -r.get("piriformis_injection_services", 0),
        -r.get("article_count", 0),
        r.get("last_name", ""),
    ))

    # Apply filters
    records = apply_filters(records, args)

    # Assign ranks after filtering
    for i, rec in enumerate(records, 1):
        rec["rank"] = i

    # Build display name
    for rec in records:
        rec["name"] = f"{rec['last_name']}, {rec['first_name']}"

    filters_desc = []
    if args.state:
        filters_desc.append(f"state={args.state}")
    if args.city:
        filters_desc.append(f"city={args.city}")
    if args.in_network_only:
        filters_desc.append("in-network only")
    if args.exclude_zip_only:
        filters_desc.append("excluding zip-only")
    if args.min_score > 0:
        filters_desc.append(f"score>={args.min_score}")
    if args.top:
        filters_desc.append(f"top {args.top}")

    print(f"\n{len(records)} providers after filtering"
          + (f" ({', '.join(filters_desc)})" if filters_desc else ""))

    # Save JSON
    out_json = DATA_DIR / "ranked_physicians.json"
    with open(out_json, "w") as f:
        json.dump(records, f, indent=2)
    print(f"\nWrote {out_json}")

    # Save CSV
    csv_fields = [
        "rank", "npi", "name", "credential", "specialty",
        "city", "state", "zip", "address",
        "score", "reasons",
        "article_count", "in_anthem_network", "accepting_new_patients",
        "anthem_networks",
        "weighted_procedure_score", "piriformis_injection_services",
        "colleague_match_confidence", "colleague_match_type",
        "sources",
    ]
    out_csv = DATA_DIR / "ranked_physicians.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            row = dict(rec)
            row["reasons"] = "; ".join(rec.get("reasons", []))
            row["anthem_networks"] = "; ".join(rec.get("anthem_networks", []))
            row["sources"] = ", ".join(rec.get("sources", []))
            writer.writerow(row)
    print(f"Wrote {out_csv}")

    # Console summary
    print_summary(records)


if __name__ == "__main__":
    main()
