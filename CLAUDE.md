# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Physician Search — a tool to help patients find appropriate in-network physicians for specific medical conditions. The initial use case focuses on piriformis syndrome diagnosis and treatment.

## Status

Two-stage pipeline is functional. See [ROADMAP.md](ROADMAP.md) for what's done, what's next, and open problems.

## Architecture

Two standalone Python scripts with inline `uv` dependency metadata (no pyproject.toml):

- `fetch_authors.py` — Searches PubMed E-utilities API, parses article XML with `lxml`, deduplicates authors. Outputs `data/authors.json` and `data/articles.json`.
- `lookup_npis.py` — Reads `data/authors.json`, queries NPPES REST API by name, matches against relevant specialty taxonomy codes. Outputs `data/physicians.csv` and `data/physicians.json`.

Both scripts use `httpx` for HTTP and respect API rate limits (~0.3-0.4s between requests).

## Tooling

- Python scripts run via `uv run` (inline dependencies, no virtual env setup needed)
- `uv` cache may need `UV_CACHE_DIR` set to a writable path in sandboxed environments
- Data outputs go to `data/` (gitignored)

## Running

```bash
uv run fetch_authors.py        # Stage 1: PubMed search (~2 min)
uv run lookup_npis.py          # Stage 2: NPI lookup (~5 min)
```
