# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Physician Search — a tool to help patients find appropriate in-network physicians for specific medical conditions. The initial use case focuses on piriformis syndrome diagnosis and treatment.

## Status

Seven scripts in `scripts/` (six pipeline stages + one shared module) across three parallel pipelines plus a merge/rank step. Each pipeline script exposes a `run()` function. A top-level `main.py` orchestrator chains all pipelines together, passing data in-memory and re-scoring after Anthem network checks. See [plans/ROADMAP.md](plans/ROADMAP.md) for what's done, what's next, and open problems. See `plans/` for implementation plans for upcoming work.

## Architecture

Seven standalone Python scripts in `scripts/` with inline `uv` dependency metadata (no pyproject.toml). Each pipeline script exposes a `run()` function that accepts input data and returns output data; `main()` is a thin CLI wrapper handling file I/O.

**Shared infrastructure:**
- `scripts/cms_db.py` — CMS Medicare data management via DuckDB. Downloads the CMS Provider Utilization CSV (~300 MB) once, imports into a compressed DuckDB database (`data/cms/cms.duckdb`, ~50-80 MB), and provides fast SQL queries for all pipeline stages. Also provides concurrent async NPPES batch query utilities and shared constants (specialty codes, taxonomy codes, HCPCS codes). Used by stages 2, 3, and 4.

**Pipeline A — publication-based:**
- `scripts/fetch_authors.py` — Searches PubMed E-utilities API, parses article XML with `lxml`, deduplicates authors. Outputs `data/authors.json` and `data/articles.json`.
- `scripts/lookup_npis.py` — Reads `data/authors.json`, matches authors to NPIs using CMS DuckDB for fast name lookup, falls back to concurrent NPPES API queries for misses. Outputs `data/physicians.csv` and `data/physicians.json`.
- `scripts/check_anthem_network.py` — Reads `data/physicians.json`, filters to Cook County IL, queries Anthem/Elevance FHIR Provider Directory (DaVinci Plan-Net IG) by name, matches on NPI, extracts network affiliations from FHIR extensions. Outputs `data/in_network_physicians.csv` and `data/in_network_physicians.json`. Requires `.env` with Anthem OAuth2 credentials.

**Pipeline B — procedure-volume-based (independent):**
- `scripts/find_by_procedures.py` — Queries the CMS DuckDB database for relevant HCPCS codes (weighted: 27096 piriformis injection = 10x, trigger point/nerve procedures = 1-2x), ranks providers by weighted score, enriches via concurrent NPPES if needed, cross-references against published authors. Supports `--state`, `--city`, `--min-score`, `--top` flags. Outputs `data/procedure_physicians.csv` and `data/procedure_physicians.json`.

**Pipeline C — practice-colleague-based (independent):**
- `scripts/find_practice_colleagues.py` — Reads `data/physicians.json` seed physicians (relevant-specialty + NPI), extracts their zip codes, uses CMS DuckDB to find relevant-specialty providers in those zips, then fetches street addresses via concurrent NPPES queries for address matching. Exact address matches = high confidence colleagues; same-zip + relevant-specialty = weaker signal. Flags probable hospital-campus addresses (>20 providers at one address) with lower confidence. Supports `--state`, `--match-type` (address|zip|both), `--hospital-threshold` flags. Outputs `data/practice_colleagues.csv` and `data/practice_colleagues.json`.

**Merge & Rank:**
- `scripts/merge_and_rank.py` — Full outer join on NPI across all pipelines, computes composite scores, applies filters, outputs `data/ranked_physicians.csv` and `data/ranked_physicians.json`.

All NPPES API queries use concurrent async HTTP (`httpx.AsyncClient` with semaphore, ~10 concurrent requests) via `batch_nppes()` in `cms_db.py`. CMS data is queried via DuckDB SQL (sub-second) instead of scanning CSV files. Shared constants (`RELEVANT_TAXONOMIES`, `RELEVANT_CMS_SPECIALTIES`, `TARGET_HCPCS`) live in `cms_db.py` — do not duplicate them in other scripts.

## Tooling

- Python scripts run via `uv run` (inline dependencies, no virtual env setup needed)
- `uv` cache may need `UV_CACHE_DIR` set to a writable path in sandboxed environments
- Scripts importable via `sys.path.insert(0, 'scripts')` for use by `main.py`
- `DATA_DIR = Path("data")` is CWD-relative; run scripts from project root
- Data outputs go to `data/` (gitignored)
- CMS DuckDB database stored at `data/cms/cms.duckdb` (gitignored, auto-created on first run)
- Anthem API credentials stored in `.env` (gitignored), loaded via `python-dotenv`

## Running

```bash
# Full pipeline (recommended)
uv run main.py --state IL --top 200        # Run all stages, check top 200 against Anthem
uv run main.py --state IL --top 10         # Quick test (limits Anthem API calls)

# Force re-download and re-import of CMS data (e.g. when new year's data is released)
uv run main.py --state IL --refresh-cms

# Manual CMS CSV URL override
uv run main.py --state IL --cms-url https://data.cms.gov/...csv
```

Individual scripts still work standalone:

```bash
# Pipeline A
uv run scripts/fetch_authors.py            # Stage 1: PubMed search (~2 min)
uv run scripts/lookup_npis.py              # Stage 2: NPI lookup (~30 sec with CMS DB)
uv run scripts/check_anthem_network.py     # Stage 3: Anthem network check (~1 min)

# Pipeline B (independent)
uv run scripts/find_by_procedures.py       # Stage 4: CMS procedure volume (~1 sec with DuckDB)
uv run scripts/find_by_procedures.py --state IL --city Chicago --min-score 10
uv run scripts/find_by_procedures.py --refresh-cms   # Force re-download

# Pipeline C (independent)
uv run scripts/find_practice_colleagues.py           # all states
uv run scripts/find_practice_colleagues.py --state IL --match-type address

# Merge & Rank
uv run scripts/merge_and_rank.py --state IL --exclude-zip-only
```

Stage 3 also supports `--probe` for raw API exploration:
```bash
uv run scripts/check_anthem_network.py --probe PractitionerRole practitioner=<id>
uv run scripts/check_anthem_network.py --probe InsurancePlan _count=5
```
