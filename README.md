# Physician Search

American healthcare is broken oh-so-many ways. Among other things, if you have or suspect you have a specific medical issue, it is difficult or impossible to find an appropriate in-network physician. This project attempts to solve that, with an initial use case of the author's stubborn piriformis syndrome diagnosis.

## What it does

Two parallel pipelines that identify physicians with demonstrated familiarity with a condition, then cross-references them against an insurance network.

**Pipeline A: Publication-based**

**Stage 1 — `fetch_authors.py`**: Searches PubMed for piriformis-related publications across multiple query terms, extracts all authors and affiliations, and deduplicates them. Casts a wide net: every coauthor on every relevant paper, not just first/last authors.

**Stage 2 — `lookup_npis.py`**: Queries the NPPES (National Provider Identifier) registry to find NPI numbers, credentials, specialties, and practice locations for each author. Filters to relevant specialties (PM&R, pain medicine, neurology, orthopedic surgery, neurosurgery, anesthesiology/pain).

**Stage 3 — `check_anthem_network.py`**: Filters physicians to Cook County, IL, then checks each against the Anthem/Elevance Health FHIR Provider Directory API to determine in-network status. Extracts network affiliations, accepting-new-patients status, and Anthem-side specialty data from DaVinci Plan-Net extensions.

**Pipeline B: Procedure-volume-based**

**Stage 4 — `find_by_procedures.py`**: Independently identifies physicians who *perform* piriformis-relevant procedures at high volume, using CMS Medicare Provider Utilization and Payment Data. Auto-discovers and downloads the most recent dataset (~10M rows), filters by relevant HCPCS codes (27096, 20552/20553, 64450, 64640, nerve conduction studies, etc.) with weights, and ranks providers by weighted procedure score. Cross-references results against the published-author set. Supports `--state`/`--city` filters for geographic targeting.

Outputs land in `data/`:
- `articles.json` — full article metadata (702 articles)
- `authors.json` — deduplicated author list (2,647 authors)
- `physicians.csv` / `physicians.json` — authors enriched with NPI and practice info (1,904 records, 306 with relevant specialties)
- `in_network_physicians.csv` / `in_network_physicians.json` — Cook County physicians found in Anthem's provider directory
- `procedure_physicians.csv` / `procedure_physicians.json` — physicians ranked by weighted procedure volume, with `also_published` flag for overlap with Pipeline A

## Usage

Requires [uv](https://docs.astral.sh/uv/). No project setup needed — scripts use inline dependency metadata.

```bash
# Pipeline A: publication-based
uv run fetch_authors.py            # Stage 1: ~2 min, hits PubMed API
uv run lookup_npis.py              # Stage 2: ~5 min, hits NPPES API
uv run lookup_npis.py --all        # Include international authors (slower)
uv run check_anthem_network.py     # Stage 3: ~1 min, hits Anthem FHIR API

# Pipeline B: procedure-volume-based (independent)
uv run find_by_procedures.py                        # All US, top 500 providers
uv run find_by_procedures.py --state IL --city Chicago  # Filter geographically
uv run find_by_procedures.py --min-score 20 --top 200   # Stricter filter
```

Stage 3 requires a `.env` file with Anthem API credentials (see below).

Stage 4 auto-discovers and downloads the CMS dataset (~300 MB) on first run; subsequent runs reuse the cached file in `data/cms/`.

### Anthem API credentials

Register at Anthem's developer portal to obtain credentials, then create a `.env` file in the project root:

```
ANTHEM_CLIENT_ID=...
ANTHEM_CLIENT_SECRET=...
ANTHEM_ACCESS_TOKEN_URL=...
ANTHEM_PROVIDER_DIRECTORY_URL=...
```

The `.env` file is gitignored and never committed.

## Next steps

See [ROADMAP.md](ROADMAP.md) for current status and open problems.
