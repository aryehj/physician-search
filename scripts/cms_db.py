# /// script
# requires-python = ">=3.11"
# dependencies = ["duckdb", "httpx"]
# ///
"""
Shared CMS Medicare data management via DuckDB, plus async NPPES utilities.

Provides:
- CmsDb: DuckDB-backed store for CMS Medicare Provider Utilization data
- batch_nppes(): concurrent NPPES API queries
- Shared constants (specialties, taxonomy codes, HCPCS codes)

The CMS CSV (~300 MB, ~10M rows) is imported once into a DuckDB database
(~50-80 MB compressed) and reused across pipeline stages. Subsequent runs
skip the import entirely and query the existing database in milliseconds.
"""

import asyncio
import re
from pathlib import Path

import duckdb
import httpx

DATA_DIR = Path("data")
CMS_DIR = DATA_DIR / "cms"
DB_PATH = CMS_DIR / "cms.duckdb"

NPPES_API = "https://npiregistry.cms.hhs.gov/api/"
CMS_DATA_JSON = "https://data.cms.gov/data.json"

# ---------- Shared constants ----------

# CMS specialty description strings (used for CMS data filtering)
RELEVANT_CMS_SPECIALTIES = {
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
    "Addiction Medicine",
}

# NPPES taxonomy codes (used for NPPES API result filtering)
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

# HCPCS codes relevant to piriformis syndrome, with weights
TARGET_HCPCS = {
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

# Taxonomy description search terms for NPPES zip queries
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

# Column name mapping — CMS changes column names across data years
_COLUMN_MAPPING = {
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


# ---------- CMS URL discovery and download ----------

def discover_cms_url(client: httpx.Client) -> tuple[str, str]:
    """Auto-discover the most recent CMS Physician Utilization CSV download URL.
    Returns (url, dataset_year)."""
    print("=== Discovering CMS dataset URL ===")
    try:
        resp = client.get(CMS_DATA_JSON, timeout=60.0)
        resp.raise_for_status()
        catalog = resp.json()
    except Exception as e:
        raise RuntimeError(f"CMS data.json request failed: {e}")

    datasets = catalog.get("dataset", [])
    candidates = [
        d for d in datasets
        if "physician" in d.get("title", "").lower()
        and "practitioners" in d.get("title", "").lower()
        and "provider and service" in d.get("title", "").lower()
    ]
    if not candidates:
        raise RuntimeError(
            "Could not find 'Medicare Physician & Other Practitioners "
            "- by Provider and Service' in data.cms.gov catalog"
        )

    dataset = candidates[0]
    print(f"  Found: {dataset.get('title', '')}")

    csv_url = None
    for dist in dataset.get("distribution", []):
        media_type = dist.get("mediaType", "") or dist.get("format", "")
        url = dist.get("downloadURL", "") or dist.get("accessURL", "")
        if "csv" in str(media_type).lower() and url:
            csv_url = url
            break

    if not csv_url:
        raise RuntimeError("No CSV distribution found in CMS dataset")

    filename = csv_url.split("/")[-1]
    year_match = re.search(r"_D(\d{2})_", filename)
    dataset_year = f"20{year_match.group(1)}" if year_match else "unknown"

    print(f"  Year: {dataset_year}")
    print(f"  URL: {csv_url}")
    return csv_url, dataset_year


def download_cms_csv(client: httpx.Client, url: str) -> Path:
    """Stream-download the CMS CSV to data/cms/. Skips if already downloaded."""
    CMS_DIR.mkdir(parents=True, exist_ok=True)
    filename = url.split("/")[-1].split("?")[0] or "cms_utilization.csv"
    local_path = CMS_DIR / filename

    if local_path.exists():
        size_mb = local_path.stat().st_size / 1_000_000
        print(f"  Cached: {local_path} ({size_mb:.0f} MB)")
        return local_path

    tmp_path = local_path.with_suffix(".tmp")
    print(f"  Downloading {url}")

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
                    print(
                        f"\r  {downloaded / 1e6:.0f} / {total / 1e6:.0f} MB ({pct:.0f}%)",
                        end="", flush=True,
                    )

    tmp_path.rename(local_path)
    print(f"\n  Done: {local_path.stat().st_size / 1e6:.0f} MB")
    return local_path


# ---------- DuckDB database ----------

class CmsDb:
    """DuckDB-backed CMS Medicare provider utilization data store."""

    _PROVIDER_COLS = [
        "npi", "first_name", "last_name", "credential",
        "specialty", "city", "state", "zip",
    ]

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn

    @classmethod
    def ensure(cls, refresh: bool = False, csv_url: str | None = None) -> "CmsDb":
        """Open the existing CMS database, or download + import if needed.

        Args:
            refresh: If True, rebuild the database even if it exists.
            csv_url: Manual override URL for the CMS CSV download.
        """
        CMS_DIR.mkdir(parents=True, exist_ok=True)

        if not refresh and DB_PATH.exists():
            try:
                conn = duckdb.connect(str(DB_PATH))
                count = conn.execute("SELECT COUNT(*) FROM cms").fetchone()[0]
                print(f"CMS database: {count:,} rows ({DB_PATH})")
                return cls(conn)
            except Exception:
                print("CMS database corrupt, rebuilding...")
                DB_PATH.unlink(missing_ok=True)

        # Download CSV
        with httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "physician-search/1.0"},
            follow_redirects=True,
        ) as client:
            if csv_url:
                url = csv_url
                print(f"Using manual CMS URL: {csv_url}")
            else:
                url, _ = discover_cms_url(client)
            csv_path = download_cms_csv(client, url)

        return cls._import_csv(csv_path)

    @classmethod
    def _import_csv(cls, csv_path: Path) -> "CmsDb":
        """Import a CMS CSV into a fresh DuckDB database."""
        DB_PATH.unlink(missing_ok=True)
        conn = duckdb.connect(str(DB_PATH))

        safe_path = str(csv_path).replace("'", "''")

        # Detect actual column names from the CSV header
        desc = conn.execute(f"""
            DESCRIBE SELECT * FROM read_csv_auto('{safe_path}', sample_size=1000)
        """).fetchall()
        available = {row[0].lower(): row[0] for row in desc}

        # Build SELECT with standardized column names
        select_parts = []
        for std_name, candidates in _COLUMN_MAPPING.items():
            matched = False
            for c in candidates:
                if c in available:
                    orig = available[c]
                    if std_name in ("npi", "zip"):
                        select_parts.append(f'CAST("{orig}" AS VARCHAR) AS {std_name}')
                    elif std_name in ("services", "beneficiaries"):
                        select_parts.append(
                            f'TRY_CAST("{orig}" AS DOUBLE) AS {std_name}'
                        )
                    else:
                        select_parts.append(f'"{orig}" AS {std_name}')
                    matched = True
                    break
            if not matched:
                if std_name in ("services", "beneficiaries"):
                    select_parts.append(f"CAST(0 AS DOUBLE) AS {std_name}")
                else:
                    select_parts.append(f"NULL AS {std_name}")

        select_sql = ", ".join(select_parts)

        print(f"\nImporting {csv_path.name} into DuckDB...")
        conn.execute(f"""
            CREATE TABLE cms AS
            SELECT {select_sql}
            FROM read_csv_auto('{safe_path}', header=true, ignore_errors=true)
        """)

        count = conn.execute("SELECT COUNT(*) FROM cms").fetchone()[0]
        print(f"  {count:,} rows imported")

        print("  Creating indexes...")
        conn.execute("CREATE INDEX idx_cms_npi ON cms(npi)")
        conn.execute("CREATE INDEX idx_cms_hcpcs ON cms(hcpcs_code)")

        db_size = DB_PATH.stat().st_size / 1e6
        print(f"  Database: {DB_PATH} ({db_size:.0f} MB)")

        return cls(conn)

    # ----- SQL helpers -----

    def _specialty_filter_sql(self) -> str:
        """SQL WHERE fragment matching relevant CMS specialties (substring)."""
        conditions = [f"specialty ILIKE '%{s}%'" for s in RELEVANT_CMS_SPECIALTIES]
        return "(" + " OR ".join(conditions) + ")"

    def _hcpcs_filter_sql(self) -> str:
        """SQL WHERE fragment matching target HCPCS codes."""
        codes = ", ".join(f"'{c}'" for c in TARGET_HCPCS)
        return f"hcpcs_code IN ({codes})"

    # ----- Query methods -----

    def lookup_by_name(self, first_name: str, last_name: str) -> list[dict]:
        """Find unique providers by name. Uses first token of first_name for
        broad matching. Returns list of provider dicts."""
        first = first_name.split()[0] if first_name else ""
        if not first or not last_name:
            return []

        rows = self.conn.execute("""
            SELECT DISTINCT npi, first_name, last_name, credential,
                   specialty, city, state, zip
            FROM cms
            WHERE lower(last_name) = lower($1)
              AND lower(first_name) LIKE lower($2) || '%'
        """, [last_name, first]).fetchall()

        return [dict(zip(self._PROVIDER_COLS, row)) for row in rows]

    def lookup_by_npi(self, npi: str) -> dict | None:
        """Find a single provider by NPI number."""
        rows = self.conn.execute("""
            SELECT DISTINCT npi, first_name, last_name, credential,
                   specialty, city, state, zip
            FROM cms WHERE npi = $1
        """, [str(npi)]).fetchall()

        if not rows:
            return None
        return dict(zip(self._PROVIDER_COLS, rows[0]))

    def providers_in_zip(self, zip_code: str, relevant_only: bool = True) -> list[dict]:
        """Find unique providers in a zip code, optionally filtered to relevant
        specialties."""
        if relevant_only:
            extra = f" AND {self._specialty_filter_sql()}"
        else:
            extra = ""

        rows = self.conn.execute(f"""
            SELECT DISTINCT npi, first_name, last_name, credential,
                   specialty, city, state, zip
            FROM cms
            WHERE zip = $1{extra}
        """, [zip_code]).fetchall()

        return [dict(zip(self._PROVIDER_COLS, row)) for row in rows]

    def procedure_volume(
        self,
        state: str | None = None,
        city: str | None = None,
    ) -> dict[str, dict]:
        """Get procedure volume for relevant HCPCS codes, aggregated by
        (NPI, HCPCS code).

        Returns dict: {npi: {npi, last_name, first_name, credential, specialty,
        city, state, zip, codes: {code: {services, beneficiaries}},
        total_weighted_score}}.
        """
        conditions = [self._hcpcs_filter_sql(), self._specialty_filter_sql()]
        params = []

        if state:
            params.append(state)
            conditions.append(f"upper(state) = upper(${len(params)})")
        if city:
            params.append(city)
            conditions.append(f"upper(city) = upper(${len(params)})")

        where = " AND ".join(conditions)

        rows = self.conn.execute(f"""
            SELECT npi, hcpcs_code,
                   CAST(COALESCE(SUM(COALESCE(services, 0)), 0) AS INTEGER)
                       AS total_services,
                   CAST(COALESCE(SUM(COALESCE(beneficiaries, 0)), 0) AS INTEGER)
                       AS total_beneficiaries,
                   last_name, first_name, credential, specialty,
                   city, state, zip
            FROM cms
            WHERE {where}
            GROUP BY npi, hcpcs_code, last_name, first_name, credential,
                     specialty, city, state, zip
        """, params).fetchall()

        providers: dict[str, dict] = {}
        for row in rows:
            npi = row[0]
            code = row[1]
            services = row[2]
            beneficiaries = row[3]

            if npi not in providers:
                providers[npi] = {
                    "npi": npi,
                    "last_name": row[4] or "",
                    "first_name": row[5] or "",
                    "credential": row[6] or "",
                    "specialty": row[7] or "",
                    "city": row[8] or "",
                    "state": row[9] or "",
                    "zip": row[10] or "",
                    "codes": {},
                    "total_weighted_score": 0.0,
                }

            providers[npi]["codes"][code] = {
                "services": services,
                "beneficiaries": beneficiaries,
            }
            providers[npi]["total_weighted_score"] += (
                services * TARGET_HCPCS.get(code, 1)
            )

        return providers

    def close(self):
        self.conn.close()


# ---------- NPPES helpers ----------

def is_relevant_taxonomy(taxonomies: list[dict]) -> bool:
    """Check if any taxonomy code is in RELEVANT_TAXONOMIES."""
    return any(t.get("code", "") in RELEVANT_TAXONOMIES for t in taxonomies)


def is_relevant_cms_specialty(specialty: str) -> bool:
    """Check if a CMS specialty string matches any RELEVANT_CMS_SPECIALTIES
    (substring match, case-insensitive)."""
    if not specialty:
        return False
    sl = specialty.lower()
    return any(s.lower() in sl for s in RELEVANT_CMS_SPECIALTIES)


def parse_nppes_result(r: dict) -> dict:
    """Parse a single NPPES API result record into a normalized dict."""
    basic = r.get("basic", {})
    taxonomies = r.get("taxonomies", [])

    specialties = []
    is_relevant = False
    for tax in taxonomies:
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

    addr = None
    for a in r.get("addresses", []):
        if a.get("address_purpose") == "LOCATION":
            addr = {
                "address_1": a.get("address_1", ""),
                "address_2": a.get("address_2", ""),
                "city": a.get("city", ""),
                "state": a.get("state", ""),
                "postal_code": a.get("postal_code", "")[:5],
            }
            break

    return {
        "npi": r.get("number"),
        "first_name": basic.get("first_name", ""),
        "last_name": basic.get("last_name", ""),
        "credential": basic.get("credential", ""),
        "gender": basic.get("gender", ""),
        "specialty": primary_spec,
        "specialties": specialties,
        "is_relevant_specialty": is_relevant,
        "practice_address": addr,
        "enumeration_date": basic.get("enumeration_date", ""),
    }


# ---------- Async NPPES batch queries ----------

async def _nppes_request(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    params: dict,
) -> dict:
    """Single NPPES API request with concurrency control."""
    async with sem:
        try:
            resp = await client.get(
                NPPES_API, params={"version": "2.1", **params}
            )
            resp.raise_for_status()
            await asyncio.sleep(0.05)  # small courtesy delay
            return resp.json()
        except Exception as e:
            return {"error": str(e), "result_count": 0, "results": []}


async def _batch_nppes(
    param_list: list[dict], max_concurrent: int = 10
) -> list[dict]:
    """Run NPPES queries concurrently with a semaphore limit."""
    sem = asyncio.Semaphore(max_concurrent)
    async with httpx.AsyncClient(timeout=15.0) as client:
        tasks = [_nppes_request(client, sem, p) for p in param_list]
        return await asyncio.gather(*tasks)


def batch_nppes(
    param_list: list[dict], max_concurrent: int = 10
) -> list[dict]:
    """Query NPPES API concurrently for multiple parameter sets.

    Args:
        param_list: List of dicts, each containing query params
            (e.g. {"first_name": ..., "last_name": ...} or {"number": npi}).
        max_concurrent: Max simultaneous requests (default 10).

    Returns:
        List of raw NPPES API JSON responses, one per input query.
    """
    if not param_list:
        return []
    return asyncio.run(_batch_nppes(param_list, max_concurrent))
