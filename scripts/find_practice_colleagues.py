# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "duckdb"]
# ///
"""
Find physicians who work at the same practice location as known published experts.

If Dr. A publishes on piriformis syndrome and Dr. B works in the same pain
management office, Dr. B likely has relevant experience too.

When a CMS DuckDB database is available, uses it to quickly identify
relevant-specialty providers in seed zip codes, then fetches street addresses
from NPPES concurrently for address matching.

Reads:   data/physicians.json (from lookup_npis.py)
Outputs: data/practice_colleagues.csv
         data/practice_colleagues.json

Usage: uv run find_practice_colleagues.py [--state IL]
           [--match-type address|zip|both] [--hospital-threshold 20]
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from cms_db import (
    TAXONOMY_SEARCH_TERMS,
    batch_nppes,
    parse_nppes_result,
)

DATA_DIR = Path("data")

CONFIDENCE_ORDER = {"high": 0, "low_hospital_campus": 1, "low_zip_only": 2}


def normalize_address(addr_line: str) -> str:
    """Normalize address line for comparison."""
    s = addr_line.upper().strip()
    s = re.sub(r'\b(STE|SUITE|UNIT|APT|#)\s*\w*', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def extract_zip(practice_address: str) -> str | None:
    """Extract 5-digit zip from a practice_address string."""
    if not practice_address:
        return None
    m = re.search(r'\b(\d{5})\b', practice_address)
    return m.group(1) if m else None


def extract_street(practice_address: str) -> str | None:
    """Extract street line (first comma-separated component)."""
    if not practice_address:
        return None
    return practice_address.split(',')[0].strip()


def run(
    physicians: list[dict],
    state: str | None = None,
    match_type: str = "both",
    hospital_threshold: int = 20,
    cms_db=None,
) -> list[dict]:
    """Find practice colleagues of seed physicians. Returns colleague list.

    Args:
        physicians: Physician records from lookup_npis.
        state: Optional state filter for seeds.
        match_type: "address", "zip", or "both".
        hospital_threshold: Flag addresses with this many+ providers as hospital.
        cms_db: Optional CmsDb instance for fast zip lookups.
    """
    # Seed = relevant-specialty physicians with a known NPI and practice address
    seeds = [
        p for p in physicians
        if p.get("npi_match_quality") == "relevant_specialty"
        and p.get("npi")
        and p.get("practice_address")
    ]

    if state:
        seeds = [
            p for p in seeds
            if p.get("practice_state", "").upper() == state.upper()
        ]
        print(f"Loaded {len(seeds)} seed physicians in {state.upper()}")
    else:
        print(f"Loaded {len(seeds)} seed physicians with relevant specialties")

    if not seeds:
        print("No seed physicians found.")
        return []

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

    zip_list = sorted(zip_to_seeds.keys())
    print(f"Searching {len(zip_list)} unique zip codes\n")

    # --- Discover providers in each zip ---
    # Strategy: if CMS DB available, use it to find NPIs, then batch-query
    # NPPES for street addresses. Otherwise, batch-query NPPES by zip+taxonomy.

    # Maps: zip -> {npi: provider_dict}
    zip_providers: dict[str, dict[str, dict]] = {}

    if cms_db:
        # Phase 1: CMS DB lookup for all zips at once (instant)
        print("=== CMS database lookup for zip providers ===")
        all_cms_npis = set()
        for zip_code in zip_list:
            results = cms_db.providers_in_zip(zip_code, relevant_only=True)
            zip_providers[zip_code] = {}
            for r in results:
                npi = r["npi"]
                if npi:
                    zip_providers[zip_code][npi] = {
                        "npi": npi,
                        "first_name": r.get("first_name", ""),
                        "last_name": r.get("last_name", ""),
                        "credential": r.get("credential", ""),
                        "specialty": r.get("specialty"),
                        "is_relevant_specialty": True,
                        "practice_address": None,  # need NPPES for this
                    }
                    all_cms_npis.add(npi)

        total_providers = sum(len(v) for v in zip_providers.values())
        print(f"  Found {total_providers} providers across {len(zip_list)} zips")

        # Phase 2: Batch NPPES by NPI for street addresses
        # Only query non-seed NPIs (we don't need addresses for seeds)
        npis_needing_address = all_cms_npis - seed_npis
        if npis_needing_address:
            print(
                f"\n=== Fetching addresses for {len(npis_needing_address)} "
                f"providers via NPPES (concurrent) ==="
            )
            npi_list = list(npis_needing_address)
            param_list = [
                {"number": npi, "enumeration_type": "NPI-1"}
                for npi in npi_list
            ]
            responses = batch_nppes(param_list)

            npi_to_addr = {}
            for npi, resp in zip(npi_list, responses):
                if resp.get("error") or not resp.get("results"):
                    continue
                parsed = parse_nppes_result(resp["results"][0])
                npi_to_addr[npi] = parsed.get("practice_address")

            # Merge addresses back into zip_providers
            for zip_code in zip_list:
                for npi, prov in zip_providers[zip_code].items():
                    if npi in npi_to_addr and npi_to_addr[npi]:
                        prov["practice_address"] = npi_to_addr[npi]

            errors = sum(1 for r in responses if r.get("error"))
            print(f"  Addresses resolved: {len(npi_to_addr)}, errors: {errors}")

    else:
        # Fallback: batch all NPPES zip+taxonomy queries concurrently
        print("=== Querying NPPES for zip providers (concurrent) ===")
        param_list = []
        param_keys = []  # (zip_code, term) for mapping responses back
        for zip_code in zip_list:
            zip_providers[zip_code] = {}
            for term in TAXONOMY_SEARCH_TERMS:
                param_list.append({
                    "postal_code": zip_code,
                    "taxonomy_description": term,
                    "enumeration_type": "NPI-1",
                    "limit": 200,
                })
                param_keys.append((zip_code, term))

        print(
            f"  {len(param_list)} queries "
            f"({len(zip_list)} zips × {len(TAXONOMY_SEARCH_TERMS)} terms)"
        )
        responses = batch_nppes(param_list)

        for (zip_code, _), resp in zip(param_keys, responses):
            if resp.get("error"):
                continue
            for r in resp.get("results", []):
                p = parse_nppes_result(r)
                npi = p["npi"]
                if npi and npi not in zip_providers[zip_code]:
                    zip_providers[zip_code][npi] = p

        total = sum(len(v) for v in zip_providers.values())
        errors = sum(1 for r in responses if r.get("error"))
        print(f"  Found {total} providers, {errors} query errors")

    # --- Match colleagues ---
    colleagues: dict[str, dict] = {}

    for zip_code in zip_list:
        seed_entries = zip_to_seeds[zip_code]
        providers = zip_providers.get(zip_code, {})
        new_providers = {
            npi: p for npi, p in providers.items() if npi not in seed_npis
        }

        # Flag hospital-campus addresses
        addr_counts: dict[str, int] = defaultdict(int)
        for p in providers.values():
            pa = p.get("practice_address")
            pa = pa if isinstance(pa, dict) else {}
            norm = normalize_address(pa.get("address_1", ""))
            if norm:
                addr_counts[norm] += 1
        hospital_addresses = {
            addr for addr, count in addr_counts.items()
            if count >= hospital_threshold
        }

        for npi, provider in new_providers.items():
            if not provider.get("is_relevant_specialty"):
                continue

            pa = provider.get("practice_address")
            pa = pa if isinstance(pa, dict) else {}
            provider_street = normalize_address(pa.get("address_1", ""))
            provider_city = pa.get("city", "").upper().strip()
            is_hospital = provider_street in hospital_addresses if provider_street else False

            # Check for same-address seeds
            matching_seed_npis = []
            if provider_street:
                matching_seed_npis = [
                    e["seed_npi"] for e in seed_entries
                    if provider_street == e["norm_street"]
                    and provider_city == e["city"]
                ]

            if matching_seed_npis:
                if match_type == "zip":
                    continue
                match_type_val = (
                    "same_address_hospital_campus" if is_hospital
                    else "same_address"
                )
                match_confidence = (
                    "low_hospital_campus" if is_hospital else "high"
                )
            else:
                if match_type == "address":
                    continue
                match_type_val = "same_zip_specialty"
                match_confidence = "low_zip_only"
                matching_seed_npis = [e["seed_npi"] for e in seed_entries]

            if npi in colleagues:
                existing = colleagues[npi]
                for s in matching_seed_npis:
                    if s not in existing["colleague_of"]:
                        existing["colleague_of"].append(s)
                if CONFIDENCE_ORDER.get(match_confidence, 9) < CONFIDENCE_ORDER.get(
                    existing["match_confidence"], 9
                ):
                    existing["match_type"] = match_type_val
                    existing["match_confidence"] = match_confidence
            else:
                colleagues[npi] = {
                    "npi": npi,
                    "first_name": provider.get("first_name", ""),
                    "last_name": provider.get("last_name", ""),
                    "credential": provider.get("credential", ""),
                    "specialty": provider.get("specialty", ""),
                    "practice_address_1": pa.get("address_1", ""),
                    "practice_city": pa.get("city", ""),
                    "practice_state": pa.get("state", ""),
                    "practice_zip": pa.get("postal_code", zip_code),
                    "colleague_of": list(matching_seed_npis),
                    "match_type": match_type_val,
                    "match_confidence": match_confidence,
                }

    results = list(colleagues.values())

    results.sort(key=lambda x: CONFIDENCE_ORDER.get(x["match_confidence"], 9))

    n_same_addr = sum(1 for r in results if r["match_type"] == "same_address")
    n_hospital = sum(
        1 for r in results
        if r["match_type"] == "same_address_hospital_campus"
    )
    n_zip = sum(1 for r in results if r["match_type"] == "same_zip_specialty")

    print(f"\n=== Results ===")
    print(f"  Same address (non-hospital): {n_same_addr}")
    print(f"  Same address (hospital):     {n_hospital}")
    print(f"  Same zip + specialty:        {n_zip}")
    print(f"  Total:                       {len(results)}")

    high = [r for r in results if r["match_confidence"] == "high"]
    if high:
        print(f"\n=== High-confidence matches ({len(high)}) ===")
        for r in high[:20]:
            loc = (
                f"{r['practice_address_1']}, {r['practice_city']}, "
                f"{r['practice_state']}"
            )
            print(
                f"  {r['first_name']} {r['last_name']}, "
                f"{r['credential'] or '?'} — {r['specialty']} — {loc}"
            )
        if len(high) > 20:
            print(f"  ... and {len(high) - 20} more")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Find physicians at the same practice locations as known "
        "piriformis experts."
    )
    parser.add_argument("--state", help="Filter seed physicians by state (e.g. IL)")
    parser.add_argument(
        "--match-type", choices=["address", "zip", "both"], default="both",
        help="Match type: address, zip, or both (default)",
    )
    parser.add_argument(
        "--hospital-threshold", type=int, default=20,
        help="Providers at one address before flagging as hospital (default: 20)",
    )
    args = parser.parse_args()

    physicians_path = DATA_DIR / "physicians.json"
    if not physicians_path.exists():
        print("Error: data/physicians.json not found. Run lookup_npis.py first.")
        sys.exit(1)

    with open(physicians_path) as f:
        all_physicians = json.load(f)

    # Try to use CMS DB if available
    cms_db = None
    try:
        from cms_db import CmsDb, DB_PATH
        if DB_PATH.exists():
            cms_db = CmsDb.ensure()
    except Exception as e:
        print(f"CMS database not available ({e}), using NPPES only")

    results = run(
        all_physicians,
        state=args.state,
        match_type=args.match_type,
        hospital_threshold=args.hospital_threshold,
        cms_db=cms_db,
    )

    if cms_db:
        cms_db.close()

    if not results:
        sys.exit(1)

    json_path = DATA_DIR / "practice_colleagues.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {json_path}")

    csv_path = DATA_DIR / "practice_colleagues.csv"
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


if __name__ == "__main__":
    main()
