# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Physician Search — a tool to help patients find appropriate in-network physicians for specific medical conditions. The initial use case focuses on piriformis syndrome diagnosis and treatment.

## Status

Two-stage pipeline is functional. See [plans/ROADMAP.md](plans/ROADMAP.md) for what's done, what's next, and open problems. See `plans/` for implementation plans for upcoming work.

## Architecture

Three standalone Python scripts with inline `uv` dependency metadata (no pyproject.toml):

- `fetch_authors.py` — Searches PubMed E-utilities API, parses article XML with `lxml`, deduplicates authors. Outputs `data/authors.json` and `data/articles.json`.
- `lookup_npis.py` — Reads `data/authors.json`, queries NPPES REST API by name, matches against relevant specialty taxonomy codes. Outputs `data/physicians.csv` and `data/physicians.json`.
- `check_anthem_network.py` — Reads `data/physicians.json`, filters to Cook County IL, queries Anthem/Elevance FHIR Provider Directory (DaVinci Plan-Net IG) by name, matches on NPI, extracts network affiliations from FHIR extensions. Outputs `data/in_network_physicians.csv` and `data/in_network_physicians.json`. Requires `.env` with Anthem OAuth2 credentials.

All scripts use `httpx` for HTTP and respect API rate limits (~0.3-0.4s between requests).

## Tooling

- Python scripts run via `uv run` (inline dependencies, no virtual env setup needed)
- `uv` cache may need `UV_CACHE_DIR` set to a writable path in sandboxed environments
- Data outputs go to `data/` (gitignored)
- Anthem API credentials stored in `.env` (gitignored), loaded via `python-dotenv`

## Running

```bash
uv run fetch_authors.py            # Stage 1: PubMed search (~2 min)
uv run lookup_npis.py              # Stage 2: NPI lookup (~5 min)
uv run check_anthem_network.py     # Stage 3: Anthem network check (~1 min)
```

Stage 3 also supports `--probe` for raw API exploration:
```bash
uv run check_anthem_network.py --probe PractitionerRole practitioner=<id>
uv run check_anthem_network.py --probe InsurancePlan _count=5
```
