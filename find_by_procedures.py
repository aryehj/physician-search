# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
Stage 4: Find physicians who frequently perform piriformis-relevant procedures,
using CMS Medicare Provider Utilization and Payment Data.

Reads:   data/physicians.json (optional, to flag published authors)
Outputs: data/procedure_physicians.json
         data/procedure_physicians.csv

Usage: uv run find_by_procedures.py [--state IL] [--city Chicago] [--min-score 10] [--url URL]
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import httpx

DATA_DIR = Path("data")
CMS_DIR = DATA_DIR / "cms"

# HCPCS codes relevant to piriformis syndrome, with weights.
# Weight rationale: 27096 is the only truly piriformis-specific code;
# all others are general musculoskeletal/pain procedures.
TARGET_CODES = {
    "27096": 10,  # Injection; sacroiliac joint/piriformis — most specific
    "20552": 2,   # Trigger point injection(s), 1-2 muscles
    "20553": 2,   # Trigger point injection(s), 3+ muscles
    "64450": 1,   # Injection, anesthetic; other peripheral nerve
    "64640": 1,   # Destruction by neurolytic agent; other peripheral nerve
    "95907": 1,   # Nerve conduction study, 1-2 studies
    "95908": 1,   # Nerve conduction study, 3-4 studies
    "95909": 1,   # Nerve conduction study, 5-6 studies
    "95910": 1,   # Nerve conduction study, 7-8 studies
    "95911": 1,   # Nerve conduction study, 9-10 studies
    "95912": 1,   # Nerve conduction study, 11-12 studies
    "95913": 1,   # Nerve conduction study, 13+ studies
    "64493": 1,   # Paravertebral facet joint injection, lumbar/sacral
    "76942": 1,   # Ultrasound guidance for needle placement
    "77003": 1,   # Fluoroscopic guidance for needle placement
}

# CMS specialty descriptions to include — skip rows not in these specialties.
# This dramatically reduces processing time on the ~10M row file.
RELEVANT_SPECIALTIES = {
    "Physical Medicine and Rehabilitation",
    "Pain Management",
    "Neurology",
    "Orthopedic Surgery",
    "Neurological Surgery",
    "Anesthesiology",
    "Sports Medicine",
    "Interventional Radiology",
    "Interventional Pain Management",
    "Osteopathic Manipulative Medicine",
    "Neuromuscular Medicine",
    "Addiction Medicine",  # sometimes overlaps pain management
}

# NPPES taxonomy codes for relevant specialties (from lookup_npis.py)
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
    "207X00000X": "Orthopaedic Surgery",
    "207XS0114X": "Orthopaedic Surgery - Sports Medicine",
    "207T00000X": "Neurological Surgery",
    "207L00000X": "Anesthesiology",
    "207LP2900X": "Anesthesiology - Pain Medicine",
    "204C00000X": "Sports Medicine",
    "2085R0001X": "Radiology - Interventional",
}

NPPES_API = "https://npiregistry.cms.hhs.gov/api/"

# CMS CKAN-style catalog endpoint
CMS_DATA_JSON = "https://data.cms.gov/data.json"


def discover_cms_url(client: httpx.Client) -> tuple[str, str]:
    """
    Auto-discover the most recent CMS Physician Utilization CSV download URL.
    Uses data.cms.gov/data.json (the federal data catalog endpoint).
    Returns (url, dataset_year).
    Raises RuntimeError if auto-discovery fails.
    """
    print("=== Discovering CMS dataset URL ===")

    try:
        resp = client.get(CMS_DATA_JSON, timeout=60.0)
        resp.raise_for_status()
        catalog = resp.json()
    except Exception as e:
        raise RuntimeError(f"CMS data.json request failed: {e}")

    datasets = catalog.get("dataset", [])
    if not datasets:
        raise RuntimeError("No datasets found in data.cms.gov/data.json")

    # Target: "Medicare Physician & Other Practitioners - by Provider and Service"
    # This is the per-(NPI, HCPCS) utilization dataset.
    candidates = [
        d for d in datasets
        if "physician" in d.get("title", "").lower()
        and "practitioners" in d.get("title", "").lower()
        and "provider and service" in d.get("title", "").lower()
    ]

    if not candidates:
        raise RuntimeError(
            "Could not find 'Medicare Physician & Other Practitioners - by Provider and Service' "
            "in data.cms.gov/data.json. "
            f"Dataset titles available: {[d.get('title') for d in datasets[:10]]}"
        )

    # There's typically one entry with multiple years as distributions.
    # Pick the first (and usually only) match.
    dataset = candidates[0]
    title = dataset.get("title", "")
    print(f"  Found dataset: {title}")

    # Find the most recent CSV distribution.
    # Distributions are ordered newest→oldest; take the first CSV hit.
    csv_url = None
    for dist in dataset.get("distribution", []):
        media_type = dist.get("mediaType", "") or dist.get("format", "")
        url = dist.get("downloadURL", "") or dist.get("accessURL", "")
        if "csv" in str(media_type).lower() and url:
            csv_url = url
            break  # first CSV = most recent year

    if not csv_url:
        raise RuntimeError(
            f"No CSV distribution found in dataset '{title}'. "
            f"Distributions: {dataset.get('distribution', [])[:3]}"
        )

    # Extract data year from filename (e.g., MUP_PHY_R25_P05_V20_D23_Prov_Svc.csv → 2023)
    filename = csv_url.split("/")[-1]
    dataset_year = "unknown"
    year_match = re.search(r"_D(\d{2})_", filename)
    if year_match:
        dataset_year = "20" + year_match.group(1)

    print(f"  Data year: {dataset_year}")
    print(f"  URL: {csv_url}")
    return csv_url, dataset_year


def download_cms_file(client: httpx.Client, url: str) -> Path:
    """
    Stream-download the CMS utilization CSV to data/cms/.
    Skip if already downloaded. Returns the local file path.
    """
    CMS_DIR.mkdir(parents=True, exist_ok=True)
    filename = url.split("/")[-1].split("?")[0] or "cms_utilization.csv"
    local_path = CMS_DIR / filename

    if local_path.exists():
        size_mb = local_path.stat().st_size / 1_000_000
        print(f"  Already downloaded: {local_path} ({size_mb:.0f} MB)")
        return local_path

    tmp_path = local_path.with_suffix(".tmp")
    print(f"  Downloading {url}")
    print(f"  Saving to {local_path}")

    with client.stream("GET", url, timeout=600.0, follow_redirects=True) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1_024 * 1_024):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = 100 * downloaded / total
                    mb = downloaded / 1_000_000
                    print(f"\r  {mb:.0f} MB / {total / 1_000_000:.0f} MB ({pct:.0f}%)", end="", flush=True)

    tmp_path.rename(local_path)
    print(f"\n  Done. {local_path.stat().st_size / 1_000_000:.0f} MB")
    return local_path


def scan_utilization_file(
    csv_path: Path,
    state_filter: str | None,
    city_filter: str | None,
) -> dict[str, dict]:
    """
    Stream-read the CMS CSV and accumulate weighted scores per NPI.
    Returns {npi: {codes: {code: {services, beneficiaries}}, total_weighted_score, name, specialty, state, city}}.
    """
    print(f"\n=== Scanning {csv_path.name} ===")

    # Detect column names from header
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = [col.strip().lower() for col in next(reader)]

    print(f"  Columns detected: {len(header)}")

    # Map column names — CMS changes these slightly by year
    col = {}
    mappings = {
        "npi": ["rndrng_npi", "npi"],
        "last_name": ["rndrng_prvdr_last_org_name", "nppes_provider_last_org_name", "last_org_name"],
        "first_name": ["rndrng_prvdr_first_name", "nppes_provider_first_name", "first_name"],
        "credential": ["rndrng_prvdr_crdntls", "nppes_credentials", "credentials"],
        "specialty": ["rndrng_prvdr_type", "provider_type", "specialty_description"],
        "city": ["rndrng_prvdr_city", "nppes_provider_city", "city"],
        "state": ["rndrng_prvdr_state_abrvtn", "nppes_provider_state", "state"],
        "zip": ["rndrng_prvdr_zip5", "nppes_provider_zip", "zip_code"],
        "hcpcs_code": ["hcpcs_cd", "hcpcs_code"],
        "services": ["tot_srvcs", "line_srvc_cnt", "services"],
        "beneficiaries": ["tot_benes", "bene_unique_cnt", "beneficiaries"],
    }
    for field, candidates in mappings.items():
        for candidate in candidates:
            if candidate in header:
                col[field] = header.index(candidate)
                break

    required = ["npi", "hcpcs_code", "services", "specialty"]
    missing = [f for f in required if f not in col]
    if missing:
        print(f"  ERROR: Could not find required columns: {missing}")
        print(f"  Available columns (first 20): {header[:20]}")
        sys.exit(1)

    print(f"  Column mapping: { {k: header[v] for k, v in col.items()} }")

    providers: dict[str, dict] = {}
    rows_read = 0
    rows_matched = 0
    rows_skipped_specialty = 0

    state_filter_upper = state_filter.upper() if state_filter else None
    city_filter_upper = city_filter.upper() if city_filter else None

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # skip header

        for row in reader:
            rows_read += 1

            if rows_read % 500_000 == 0:
                print(
                    f"  ... {rows_read:,} rows read, {rows_matched:,} matched, "
                    f"{len(providers):,} providers accumulated"
                )

            if len(row) <= max(col.values()):
                continue

            # Pre-filter by specialty
            specialty = row[col["specialty"]].strip() if "specialty" in col else ""
            if specialty and not any(
                s.lower() in specialty.lower() for s in RELEVANT_SPECIALTIES
            ):
                rows_skipped_specialty += 1
                continue

            # Pre-filter by state
            if state_filter_upper and "state" in col:
                row_state = row[col["state"]].strip().upper()
                if row_state and row_state != state_filter_upper:
                    continue

            # Pre-filter by city
            if city_filter_upper and "city" in col:
                row_city = row[col["city"]].strip().upper()
                if row_city and row_city != city_filter_upper:
                    continue

            # Check HCPCS code
            hcpcs = row[col["hcpcs_code"]].strip()
            if hcpcs not in TARGET_CODES:
                continue

            npi = row[col["npi"]].strip()
            if not npi:
                continue

            try:
                services = int(float(row[col["services"]].strip() or "0"))
            except (ValueError, IndexError):
                services = 0

            try:
                beneficiaries = int(float(row[col["beneficiaries"]].strip() or "0")) if "beneficiaries" in col else 0
            except (ValueError, IndexError):
                beneficiaries = 0

            rows_matched += 1

            if npi not in providers:
                providers[npi] = {
                    "npi": npi,
                    "last_name": row[col["last_name"]].strip() if "last_name" in col else "",
                    "first_name": row[col["first_name"]].strip() if "first_name" in col else "",
                    "credential": row[col["credential"]].strip() if "credential" in col else "",
                    "specialty": specialty,
                    "city": row[col["city"]].strip() if "city" in col else "",
                    "state": row[col["state"]].strip() if "state" in col else "",
                    "zip": row[col["zip"]].strip() if "zip" in col else "",
                    "codes": {},
                    "total_weighted_score": 0.0,
                }

            entry = providers[npi]
            if hcpcs not in entry["codes"]:
                entry["codes"][hcpcs] = {"services": 0, "beneficiaries": 0}
            entry["codes"][hcpcs]["services"] += services
            entry["codes"][hcpcs]["beneficiaries"] += beneficiaries
            entry["total_weighted_score"] += services * TARGET_CODES[hcpcs]

    print(f"\n  Rows read:               {rows_read:,}")
    print(f"  Rows skipped (specialty): {rows_skipped_specialty:,}")
    print(f"  Rows matched:            {rows_matched:,}")
    print(f"  Unique providers:        {len(providers):,}")

    return providers


def load_published_npis() -> set[str]:
    """Load NPIs from the PubMed-derived physicians.json, if it exists."""
    path = DATA_DIR / "physicians.json"
    if not path.exists():
        return set()
    with open(path) as f:
        physicians = json.load(f)
    return {p["npi"] for p in physicians if p.get("npi")}


def query_nppes(client: httpx.Client, npi: str) -> dict | None:
    """Query NPPES by NPI number to get current name/address/specialty."""
    try:
        resp = client.get(
            NPPES_API,
            params={"version": "2.1", "number": npi, "enumeration_type": "NPI-1"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    results = data.get("results", [])
    if not results:
        return None

    r = results[0]
    basic = r.get("basic", {})

    taxonomies = r.get("taxonomies", [])
    primary_spec = None
    is_relevant = False
    for tax in taxonomies:
        code = tax.get("code", "")
        if code in RELEVANT_TAXONOMIES:
            is_relevant = True
        if tax.get("primary"):
            primary_spec = tax.get("desc", "")

    addresses = r.get("addresses", [])
    addr = next((a for a in addresses if a.get("address_purpose") == "LOCATION"), None)

    return {
        "first_name": basic.get("first_name", ""),
        "last_name": basic.get("last_name", ""),
        "credential": basic.get("credential", ""),
        "specialty": primary_spec or "",
        "is_relevant_specialty": is_relevant,
        "city": addr.get("city", "") if addr else "",
        "state": addr.get("state", "") if addr else "",
        "zip": addr.get("postal_code", "")[:5] if addr else "",
        "address": (
            f"{addr.get('address_1', '')}, {addr.get('city', '')}, "
            f"{addr.get('state', '')} {addr.get('postal_code', '')[:5]}"
            if addr and addr.get("city")
            else None
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="Find physicians by procedure volume")
    parser.add_argument("--min-score", type=float, default=10.0, help="Minimum weighted score (default: 10)")
    parser.add_argument("--state", help="Filter to providers in this state (e.g., IL)")
    parser.add_argument("--city", help="Filter to providers in this city (e.g., Chicago)")
    parser.add_argument("--url", help="Manual override: direct CSV download URL for CMS file")
    parser.add_argument("--top", type=int, default=500, help="Max providers to enrich via NPPES (default: 500)")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    with httpx.Client(
        timeout=30.0,
        headers={"User-Agent": "physician-search/1.0 (research tool)"},
        follow_redirects=True,
    ) as client:

        # Step 0: Discover URL
        if args.url:
            csv_url = args.url
            dataset_year = "unknown"
            print(f"Using manually provided URL: {csv_url}")
        else:
            try:
                csv_url, dataset_year = discover_cms_url(client)
            except RuntimeError as e:
                print(f"\nERROR: Auto-discovery failed: {e}")
                print("\nTo proceed manually:")
                print("  1. Go to https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service")
                print("  2. Find the CSV download link for the most recent year")
                print("  3. Re-run with: uv run find_by_procedures.py --url <URL>")
                sys.exit(1)

        # Step 1: Download
        print("\n=== Downloading CMS utilization data ===")
        cms_path = download_cms_file(client, csv_url)

    # Step 2+3: Scan (no HTTP needed during scan)
    providers = scan_utilization_file(cms_path, args.state, args.city)

    # Step 4: Filter and rank
    print("\n=== Filtering and ranking ===")
    ranked = sorted(providers.values(), key=lambda p: -p["total_weighted_score"])
    ranked = [p for p in ranked if p["total_weighted_score"] >= args.min_score]
    print(f"  Providers with score >= {args.min_score}: {len(ranked):,}")

    # Load published NPIs for cross-reference
    published_npis = load_published_npis()
    print(f"  Published author NPIs loaded: {len(published_npis)}")

    # Enrich top providers via NPPES if CMS data lacks detail
    top_providers = ranked[: args.top]

    print(f"\n=== Enriching top {len(top_providers)} providers via NPPES ===")
    enriched = []
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        for i, p in enumerate(top_providers):
            npi = p["npi"]
            also_published = npi in published_npis

            # Use CMS data as baseline; enrich with NPPES only if state/city missing
            if p.get("city") and p.get("state"):
                record = {
                    "npi": npi,
                    "last_name": p["last_name"],
                    "first_name": p["first_name"],
                    "credential": p["credential"],
                    "specialty": p["specialty"],
                    "city": p["city"],
                    "state": p["state"],
                    "zip": p["zip"],
                    "address": None,
                    "is_relevant_specialty": any(
                        s.lower() in p["specialty"].lower()
                        for s in RELEVANT_SPECIALTIES
                    ),
                    "weighted_score": p["total_weighted_score"],
                    "procedure_volume": p["codes"],
                    "also_published": also_published,
                }
            else:
                nppes_data = query_nppes(client, npi)
                if nppes_data:
                    record = {
                        "npi": npi,
                        **nppes_data,
                        "weighted_score": p["total_weighted_score"],
                        "procedure_volume": p["codes"],
                        "also_published": also_published,
                    }
                else:
                    record = {
                        "npi": npi,
                        "last_name": p["last_name"],
                        "first_name": p["first_name"],
                        "credential": p["credential"],
                        "specialty": p["specialty"],
                        "city": p["city"],
                        "state": p["state"],
                        "zip": p["zip"],
                        "address": None,
                        "is_relevant_specialty": False,
                        "weighted_score": p["total_weighted_score"],
                        "procedure_volume": p["codes"],
                        "also_published": also_published,
                    }
                time.sleep(0.3)

            enriched.append(record)

            if (i + 1) % 50 == 0:
                print(f"  [{i + 1}/{len(top_providers)}] enriched...")

    print(f"  Done enriching {len(enriched)} providers")

    # Step 5: Output
    json_path = DATA_DIR / "procedure_physicians.json"
    csv_path = DATA_DIR / "procedure_physicians.csv"

    with open(json_path, "w") as f:
        json.dump(enriched, f, indent=2)
    print(f"\nSaved {json_path}")

    # CSV — flatten procedure_volume dict
    fieldnames = [
        "npi", "last_name", "first_name", "credential", "specialty",
        "city", "state", "zip", "weighted_score", "also_published",
        "is_relevant_specialty",
    ] + sorted(TARGET_CODES.keys())

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rec in enriched:
            row = {k: v for k, v in rec.items() if k != "procedure_volume"}
            for code in TARGET_CODES:
                row[code] = rec["procedure_volume"].get(code, {}).get("services", 0)
            writer.writerow(row)
    print(f"Saved {csv_path}")

    # Summary
    print(f"\n=== Top 20 by weighted score ===")
    print(f"{'Score':>8}  {'NPI':>12}  {'Name':<30}  {'Specialty':<35}  {'Location'}")
    print("-" * 120)
    for rec in enriched[:20]:
        name = f"{rec.get('first_name', '')} {rec.get('last_name', '')}".strip()
        loc = f"{rec.get('city', '')}, {rec.get('state', '')}".strip(", ")
        spec = (rec.get("specialty") or "")[:35]
        pub_flag = " *" if rec["also_published"] else ""
        print(f"  {rec['weighted_score']:>6.0f}  {rec['npi']:>12}  {name:<30}  {spec:<35}  {loc}{pub_flag}")

    published_also = sum(1 for r in enriched if r["also_published"])
    print(f"\n* = also in published-author set ({published_also} total)")
    print(f"\nDataset year: {dataset_year}")
    print(f"Min score filter: {args.min_score}")
    print(f"State filter: {args.state or 'none'}")
    print(f"City filter: {args.city or 'none'}")


if __name__ == "__main__":
    main()
