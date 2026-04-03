# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
Find physicians who work at the same practice location as known published experts.

If Dr. A publishes on piriformis syndrome and Dr. B works in the same pain
management office, Dr. B likely has relevant experience too.

Reads:   data/physicians.json (from lookup_npis.py)
Outputs: data/practice_colleagues.csv
         data/practice_colleagues.json

Usage: uv run find_practice_colleagues.py [--state IL] [--match-type address|zip|both]
                                           [--hospital-threshold 20]
"""

import argparse
import csv
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

NPPES_API = "https://npiregistry.cms.hhs.gov/api/"

RELEVANT_TAXONOMIES = {
    "208100000X": "PM&R",
    "2081P2900X": "PM&R - Pain Medicine",
    "2081P0010X": "PM&R - Pediatric Rehab",
    "2081S0010X": "PM&R - Sports Medicine",
    "208VP0014X": "Pain Medicine",
    "2083P0500X": "Preventive Medicine - Pain Medicine",
    "2084N0400X": "Neurology",
    "2084N0402X": "Neurology - Neuromuscular",
    "2084P0800X": "Neurology - Pain Medicine",
    "2084P0805X": "Neurology - Pediatric Neurology",
    "207X00000X": "Orthopaedic Surgery",
    "207XS0114X": "Orthopaedic Surgery - Sports Medicine",
    "207XP3100X": "Orthopaedic Surgery - Pediatric",
    "207T00000X": "Neurological Surgery",
    "207L00000X": "Anesthesiology",
    "207LP2900X": "Anesthesiology - Pain Medicine",
    "204C00000X": "Sports Medicine",
    "2085R0001X": "Radiology - Interventional",
    "208600000X": "Surgery",
}

# Taxonomy description search terms — NPPES does partial matching on these
TAXONOMY_SEARCH_TERMS = [
    "Pain Medicine",
    "Physical Medicine",
    "Orthopaedic",
    "Neurological Surgery",
    "Neurology",
    "Anesthesiology",
    "Sports Medicine",
    "Interventional",
]


def normalize_address(addr_line: str) -> str:
    """Normalize address line for comparison."""
    s = addr_line.upper().strip()
    # Remove suite/unit identifiers and trailing tokens
    s = re.sub(r'\b(STE|SUITE|UNIT|APT|#)\s*\w*', '', s)
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def extract_zip(practice_address: str) -> str | None:
    """Extract 5-digit zip from a practice_address string like '123 Main St, Chicago, IL 60601'."""
    if not practice_address:
        return None
    m = re.search(r'\b(\d{5})\b', practice_address)
    return m.group(1) if m else None


def extract_street(practice_address: str) -> str | None:
    """Extract street line (first comma-separated component) from practice_address string."""
    if not practice_address:
        return None
    return practice_address.split(',')[0].strip()


def query_nppes_by_zip(client: httpx.Client, postal_code: str, taxonomy_description: str) -> list[dict]:
    """Query NPPES for individual providers by zip code and taxonomy description."""
    try:
        resp = client.get(
            NPPES_API,
            params={
                "version": "2.1",
                "postal_code": postal_code,
                "taxonomy_description": taxonomy_description,
                "enumeration_type": "NPI-1",
                "limit": 200,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        print(f"    Error querying NPPES zip={postal_code} / {taxonomy_description}: {e}")
        return []
    return data.get("results", [])


def parse_provider(r: dict) -> dict:
    """Parse an NPPES result record into a normalized provider dict."""
    basic = r.get("basic", {})

    practice_addr = None
    for addr in r.get("addresses", []):
        if addr.get("address_purpose") == "LOCATION":
            practice_addr = {
                "address_1": addr.get("address_1", ""),
                "address_2": addr.get("address_2", ""),
                "city": addr.get("city", ""),
                "state": addr.get("state", ""),
                "postal_code": addr.get("postal_code", "")[:5],
            }
            break

    specialties = []
    is_relevant = False
    for tax in r.get("taxonomies", []):
        code = tax.get("code", "")
        specialties.append({
            "code": code,
            "description": tax.get("desc", ""),
            "primary": tax.get("primary", False),
        })
        if code in RELEVANT_TAXONOMIES:
            is_relevant = True

    primary_spec = next(
        (s["description"] for s in specialties if s["primary"]),
        specialties[0]["description"] if specialties else None,
    )

    return {
        "npi": r.get("number"),
        "first_name": basic.get("first_name", ""),
        "last_name": basic.get("last_name", ""),
        "credential": basic.get("credential", ""),
        "specialty": primary_spec,
        "is_relevant_specialty": is_relevant,
        "practice_address": practice_addr,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Find physicians at the same practice locations as known piriformis experts."
    )
    parser.add_argument("--state", help="Filter seed physicians by state (e.g. IL)")
    parser.add_argument(
        "--match-type", choices=["address", "zip", "both"], default="both",
        help="Match type to include: address (same street), zip (same zip+specialty), or both (default)"
    )
    parser.add_argument(
        "--hospital-threshold", type=int, default=20,
        help="Providers at one address before flagging as hospital campus (default: 20)"
    )
    args = parser.parse_args()

    data_dir = Path("data")
    physicians_path = data_dir / "physicians.json"

    if not physicians_path.exists():
        print("Error: data/physicians.json not found. Run lookup_npis.py first.")
        sys.exit(1)

    with open(physicians_path) as f:
        all_physicians = json.load(f)

    # Seed = relevant-specialty physicians with a known NPI and practice address
    seeds = [
        p for p in all_physicians
        if p.get("npi_match_quality") == "relevant_specialty"
        and p.get("npi")
        and p.get("practice_address")
    ]

    if args.state:
        seeds = [p for p in seeds if p.get("practice_state", "").upper() == args.state.upper()]
        print(f"Loaded {len(seeds)} seed physicians in {args.state.upper()}")
    else:
        print(f"Loaded {len(seeds)} seed physicians with relevant specialties")

    if not seeds:
        print("No seed physicians found.")
        sys.exit(1)

    seed_npis = {p["npi"] for p in seeds}

    # Build map: zip_code -> list of seed location descriptors
    zip_to_seeds: dict[str, list[dict]] = defaultdict(list)
    for p in seeds:
        zip_code = extract_zip(p["practice_address"])
        street = extract_street(p["practice_address"])
        if not zip_code or not street:
            continue
        zip_to_seeds[zip_code].append({
            "seed_npi": p["npi"],
            "norm_street": normalize_address(street),
            "city": p.get("practice_city", "").upper().strip(),
            "state": p.get("practice_state", "").upper().strip(),
        })

    print(f"Searching {len(zip_to_seeds)} unique zip codes across {len(TAXONOMY_SEARCH_TERMS)} specialty terms each\n")

    colleagues: dict[str, dict] = {}  # npi -> colleague record

    with httpx.Client(timeout=15.0) as client:
        zip_list = sorted(zip_to_seeds.keys())

        for z_idx, zip_code in enumerate(zip_list):
            seed_entries = zip_to_seeds[zip_code]
            print(f"[{z_idx+1}/{len(zip_list)}] Zip {zip_code} — {len(seed_entries)} seed location(s)", end="", flush=True)

            # Collect all providers in this zip, deduplicated by NPI
            zip_providers: dict[str, dict] = {}
            for term in TAXONOMY_SEARCH_TERMS:
                for r in query_nppes_by_zip(client, zip_code, term):
                    p = parse_provider(r)
                    if p["npi"] and p["npi"] not in zip_providers:
                        zip_providers[p["npi"]] = p
                time.sleep(0.35)

            new_providers = {npi: p for npi, p in zip_providers.items() if npi not in seed_npis}
            print(f" — {len(zip_providers)} providers found, {len(new_providers)} new")

            # Flag hospital-campus addresses: too many providers at the same address
            addr_counts: dict[str, int] = defaultdict(int)
            for p in zip_providers.values():
                pa = p.get("practice_address") or {}
                norm = normalize_address(pa.get("address_1", ""))
                if norm:
                    addr_counts[norm] += 1
            hospital_addresses = {
                addr for addr, count in addr_counts.items()
                if count >= args.hospital_threshold
            }
            if hospital_addresses:
                print(f"  Flagged {len(hospital_addresses)} hospital-campus address(es) (>= {args.hospital_threshold} providers)")

            # Match each new relevant-specialty provider against seed addresses
            for npi, provider in new_providers.items():
                if not provider.get("is_relevant_specialty"):
                    continue

                pa = provider.get("practice_address") or {}
                provider_street = normalize_address(pa.get("address_1", ""))
                provider_city = pa.get("city", "").upper().strip()
                is_hospital = provider_street in hospital_addresses

                # Check for same-address seeds
                matching_seed_npis = [
                    e["seed_npi"] for e in seed_entries
                    if provider_street == e["norm_street"] and provider_city == e["city"]
                ]

                if matching_seed_npis:
                    if args.match_type == "zip":
                        continue  # address matches excluded in zip-only mode
                    match_type = "same_address_hospital_campus" if is_hospital else "same_address"
                    match_confidence = "low_hospital_campus" if is_hospital else "high"
                else:
                    if args.match_type == "address":
                        continue  # zip-only matches excluded in address-only mode
                    match_type = "same_zip_specialty"
                    match_confidence = "low_zip_only"
                    matching_seed_npis = [e["seed_npi"] for e in seed_entries]

                if npi in colleagues:
                    # Seen via another zip — merge seed list and upgrade confidence if better
                    existing = colleagues[npi]
                    for s in matching_seed_npis:
                        if s not in existing["colleague_of"]:
                            existing["colleague_of"].append(s)
                    rank = {"high": 0, "low_hospital_campus": 1, "low_zip_only": 2}
                    if rank.get(match_confidence, 9) < rank.get(existing["match_confidence"], 9):
                        existing["match_type"] = match_type
                        existing["match_confidence"] = match_confidence
                else:
                    colleagues[npi] = {
                        "npi": npi,
                        "first_name": provider["first_name"],
                        "last_name": provider["last_name"],
                        "credential": provider["credential"],
                        "specialty": provider["specialty"],
                        "practice_address_1": pa.get("address_1", ""),
                        "practice_city": pa.get("city", ""),
                        "practice_state": pa.get("state", ""),
                        "practice_zip": pa.get("postal_code", ""),
                        "colleague_of": list(matching_seed_npis),
                        "match_type": match_type,
                        "match_confidence": match_confidence,
                    }

    results = list(colleagues.values())

    # Sort: high confidence first, hospital campus next, zip-only last
    confidence_order = {"high": 0, "low_hospital_campus": 1, "low_zip_only": 2}
    results.sort(key=lambda x: confidence_order.get(x["match_confidence"], 9))

    n_same_addr = sum(1 for r in results if r["match_type"] == "same_address")
    n_hospital = sum(1 for r in results if r["match_type"] == "same_address_hospital_campus")
    n_zip = sum(1 for r in results if r["match_type"] == "same_zip_specialty")

    print(f"\n=== Results ===")
    print(f"  Same address (non-hospital): {n_same_addr}")
    print(f"  Same address (hospital):     {n_hospital}")
    print(f"  Same zip + specialty:        {n_zip}")
    print(f"  Total:                       {len(results)}")

    json_path = data_dir / "practice_colleagues.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {json_path}")

    csv_path = data_dir / "practice_colleagues.csv"
    fieldnames = [
        "npi", "first_name", "last_name", "credential", "specialty",
        "practice_address_1", "practice_city", "practice_state", "practice_zip",
        "match_type", "match_confidence", "colleague_of",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            row = {**r, "colleague_of": "; ".join(r["colleague_of"])}
            writer.writerow(row)
    print(f"Saved {csv_path}")

    high = [r for r in results if r["match_confidence"] == "high"]
    if high:
        print(f"\n=== High-confidence matches ({len(high)}) ===")
        for r in high[:20]:
            loc = f"{r['practice_address_1']}, {r['practice_city']}, {r['practice_state']}"
            print(f"  {r['first_name']} {r['last_name']}, {r['credential'] or '?'} — {r['specialty']} — {loc}")
        if len(high) > 20:
            print(f"  ... and {len(high) - 20} more")


if __name__ == "__main__":
    main()
