# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Physician Search — a tool to help patients find appropriate in-network physicians for specific medical conditions. The initial use case focuses on piriformis syndrome diagnosis and treatment.

## Status

Six scripts in `scripts/` across three parallel pipelines plus a merge/rank step. Each script exposes a `run()` function. A top-level `main.py` orchestrator chains all pipelines together, passing data in-memory and re-scoring after Anthem network checks. See [plans/ROADMAP.md](plans/ROADMAP.md) for what's done, what's next, and open problems. See `plans/` for implementation plans for upcoming work.

## Architecture

Six standalone Python scripts in `scripts/` with inline `uv` dependency metadata (no pyproject.toml). Each exposes a `run()` function that accepts input data and returns output data; `main()` is a thin CLI wrapper handling file I/O.

**Pipeline A — publication-based:**
- `scripts/fetch_authors.py` — Searches PubMed E-utilities API, parses article XML with `lxml`, deduplicates authors. Outputs `data/authors.json` and `data/articles.json`.
- `scripts/lookup_npis.py` — Reads `data/authors.json`, queries NPPES REST API by name, matches against relevant specialty taxonomy codes. Outputs `data/physicians.csv` and `data/physicians.json`.
- `scripts/check_anthem_network.py` — Reads `data/physicians.json`, filters to Cook County IL, queries Anthem/Elevance FHIR Provider Directory (DaVinci Plan-Net IG) by name, matches on NPI, extracts network affiliations from FHIR extensions. Outputs `data/in_network_physicians.csv` and `data/in_network_physicians.json`. Requires `.env` with Anthem OAuth2 credentials.

**Pipeline B — procedure-volume-based (independent):**
- `scripts/find_by_procedures.py` — Auto-discovers and downloads the CMS Medicare Provider Utilization and Payment Data CSV (~300 MB, cached to `data/cms/`), scans ~10M rows for relevant HCPCS codes (weighted: 27096 piriformis injection = 10x, trigger point/nerve procedures = 1-2x), ranks providers by weighted score, enriches via NPPES if needed, cross-references against `data/physicians.json` published authors. Supports `--state`, `--city`, `--min-score`, `--top`, `--url` flags. Outputs `data/procedure_physicians.csv` and `data/procedure_physicians.json`.

**Pipeline C — practice-colleague-based (independent):**
- `scripts/find_practice_colleagues.py` — Reads `data/physicians.json` seed physicians (relevant-specialty + NPI), extracts their zip codes, queries NPPES for all relevant-specialty providers in those zips, then matches on normalized street address. Exact address matches = high confidence colleagues; same-zip + relevant-specialty = weaker signal. Flags probable hospital-campus addresses (>20 providers at one address) with lower confidence. Supports `--state`, `--match-type` (address|zip|both), `--hospital-threshold` flags. Outputs `data/practice_colleagues.csv` and `data/practice_colleagues.json`.

**Merge & Rank:**
- `scripts/merge_and_rank.py` — Full outer join on NPI across all pipelines, computes composite scores, applies filters, outputs `data/ranked_physicians.csv` and `data/ranked_physicians.json`.

All scripts use `httpx` for HTTP and respect API rate limits (~0.3-0.4s between requests).

## Tooling

- Python scripts run via `uv run` (inline dependencies, no virtual env setup needed)
- `uv` cache may need `UV_CACHE_DIR` set to a writable path in sandboxed environments
- Scripts importable via `sys.path.insert(0, 'scripts')` for use by `main.py`
- `DATA_DIR = Path("data")` is CWD-relative; run scripts from project root
- Data outputs go to `data/` (gitignored)
- Anthem API credentials stored in `.env` (gitignored), loaded via `python-dotenv`

## Running

```bash
# Full pipeline (recommended)
uv run main.py --state IL --top 200        # Run all stages, check top 200 against Anthem
uv run main.py --state IL --top 10         # Quick test (limits Anthem API calls)
```

Individual scripts still work standalone:

```bash
# Pipeline A
uv run scripts/fetch_authors.py            # Stage 1: PubMed search (~2 min)
uv run scripts/lookup_npis.py              # Stage 2: NPI lookup (~5 min)
uv run scripts/check_anthem_network.py     # Stage 3: Anthem network check (~1 min)

# Pipeline B (independent)
uv run scripts/find_by_procedures.py       # Stage 4: CMS procedure volume (~10 min first run, downloads ~300 MB)
uv run scripts/find_by_procedures.py --state IL --city Chicago --min-score 10

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
