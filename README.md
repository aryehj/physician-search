# Physician Search

American healthcare is broken oh-so-many ways. Among other things, if you have or suspect you have a specific medical issue, it is difficult or impossible to find an appropriate in-network physician. This project attempts to solve that, with an initial use case of the author's stubborn piriformis syndrome diagnosis.

## What it does

Two-stage pipeline that identifies physicians with demonstrated familiarity with a condition, then cross-references them against an insurance network.

**Stage 1 — `fetch_authors.py`**: Searches PubMed for piriformis-related publications across multiple query terms, extracts all authors and affiliations, and deduplicates them. Casts a wide net: every coauthor on every relevant paper, not just first/last authors.

**Stage 2 — `lookup_npis.py`**: Queries the NPPES (National Provider Identifier) registry to find NPI numbers, credentials, specialties, and practice locations for each author. Filters to relevant specialties (PM&R, pain medicine, neurology, orthopedic surgery, neurosurgery, anesthesiology/pain).

Outputs land in `data/`:
- `articles.json` — full article metadata (702 articles)
- `authors.json` — deduplicated author list (2,647 authors)
- `physicians.csv` / `physicians.json` — authors enriched with NPI and practice info (1,904 records, 306 with relevant specialties)

## Usage

Requires [uv](https://docs.astral.sh/uv/). No project setup needed — scripts use inline dependency metadata.

```bash
uv run fetch_authors.py        # Stage 1: ~2 min, hits PubMed API
uv run lookup_npis.py          # Stage 2: ~5 min, hits NPPES API
uv run lookup_npis.py --all    # Include international authors (slower)
```

## Next steps

See [ROADMAP.md](ROADMAP.md) for current status and open problems.
