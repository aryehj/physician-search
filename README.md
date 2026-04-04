# Physician Search

American healthcare is broken oh-so-many ways. Among other things, if you have or suspect you have a specific medical issue, it is difficult or impossible to find an appropriate in-network physician. This project attempts to solve that, with an initial use case of the author's stubborn piriformis syndrome diagnosis.

## What it does

Three parallel pipelines that identify physicians with demonstrated familiarity with a condition, merge their results, rank by composite score, then cross-reference the top candidates against an insurance network. A single `main.py` orchestrator runs all stages end-to-end.

**Pipeline A: Publication-based**

**Stage 1 — `scripts/fetch_authors.py`**: Searches PubMed for piriformis-related publications across multiple query terms, extracts all authors and affiliations, and deduplicates them. Casts a wide net: every coauthor on every relevant paper, not just first/last authors.

**Stage 2 — `scripts/lookup_npis.py`**: Matches authors to NPI numbers using the CMS DuckDB database for fast name lookups, falling back to concurrent NPPES API queries for misses. Filters to relevant specialties (PM&R, pain medicine, neurology, orthopedic surgery, neurosurgery, anesthesiology/pain).

**Stage 3 — `scripts/check_anthem_network.py`**: Checks physicians against the Anthem/Elevance Health FHIR Provider Directory API to determine in-network status. Extracts network affiliations, accepting-new-patients status, and Anthem-side specialty data from DaVinci Plan-Net extensions. When run standalone, filters to Cook County, IL; when called from `main.py`, operates on whatever physician list is passed in.

**Pipeline B: Procedure-volume-based**

**Stage 4 — `scripts/find_by_procedures.py`**: Independently identifies physicians who *perform* piriformis-relevant procedures at high volume, querying the CMS DuckDB database. Filters by relevant HCPCS codes (27096, 20552/20553, 64450, 64640, nerve conduction studies, etc.) with weights, and ranks providers by weighted procedure score. Cross-references results against the published-author set. Supports `--state`/`--city` filters for geographic targeting.

**Pipeline C: Practice-colleague-based**

**`scripts/find_practice_colleagues.py`**: Finds physicians who share a practice location with known published experts. If Dr. A publishes on piriformis syndrome and Dr. B works at the same address, Dr. B likely has relevant experience. Takes seed physicians from Pipeline A, extracts their practice zip codes, uses CMS DuckDB to find relevant-specialty providers in those zips, then fetches street addresses via concurrent NPPES queries for address matching. Exact address matches are high-confidence; same-zip + relevant specialty is a weaker signal. Flags probable hospital campuses (>20 providers at one address) separately. Supports `--state`, `--match-type`, and `--hospital-threshold` options.

Outputs land in `data/`:
- `articles.json` — full article metadata (702 articles)
- `authors.json` — deduplicated author list (2,647 authors)
- `physicians.csv` / `physicians.json` — authors enriched with NPI and practice info (1,904 records, 306 with relevant specialties)
- `in_network_physicians.csv` / `in_network_physicians.json` — Cook County physicians found in Anthem's provider directory
- `procedure_physicians.csv` / `procedure_physicians.json` — physicians ranked by weighted procedure volume, with `also_published` flag for overlap with Pipeline A
- `practice_colleagues.csv` / `practice_colleagues.json` — physicians at the same practice locations as published experts, with `match_type` and `match_confidence` fields
- `ranked_physicians.csv` / `ranked_physicians.json` — final merged and ranked output across all pipelines, with composite scores, in-network status, and multi-pipeline combination bonuses. CSV uses human-readable headers (Publications, Procedure Score, In Network, Colleague, Combo Bonus, etc.) with atomic columns instead of a reasons blob

## Usage

Requires [uv](https://docs.astral.sh/uv/). No project setup needed — scripts use inline dependency metadata.

```bash
# Full pipeline (recommended)
uv run main.py --state IL --top 200        # Run all stages, check top 200 against Anthem
uv run main.py --state IL --top 10         # Quick test run

# Force re-download and re-import of CMS data (e.g. when new year's data is released)
uv run main.py --state IL --refresh-cms

# Manual CMS CSV URL override
uv run main.py --state IL --cms-url https://data.cms.gov/...csv
```

Individual scripts still work standalone:

```bash
# Pipeline A: publication-based
uv run scripts/fetch_authors.py            # Stage 1: ~2 min, hits PubMed API
uv run scripts/lookup_npis.py              # Stage 2: ~30 sec (CMS DB + concurrent NPPES)
uv run scripts/lookup_npis.py --all        # Include international authors
uv run scripts/check_anthem_network.py     # Stage 3: ~1 min, hits Anthem FHIR API

# Pipeline B: procedure-volume-based (independent)
uv run scripts/find_by_procedures.py                        # All US, top 500 providers
uv run scripts/find_by_procedures.py --state IL --city Chicago  # Filter geographically
uv run scripts/find_by_procedures.py --min-score 20 --top 200   # Stricter filter
uv run scripts/find_by_procedures.py --refresh-cms              # Force CMS re-download

# Pipeline C: practice-colleague-based (independent)
uv run scripts/find_practice_colleagues.py                  # All states
uv run scripts/find_practice_colleagues.py --state IL --match-type address  # Address matches only

# Merge & rank all pipelines
uv run scripts/merge_and_rank.py --state IL --exclude-zip-only
```

Stage 3 requires a `.env` file with Anthem API credentials (see below).

On first run, the pipeline auto-discovers and downloads the CMS Medicare dataset (~300 MB), imports it into a DuckDB database (`data/cms/cms.duckdb`, ~50-80 MB compressed), and reuses it on subsequent runs. Pass `--refresh-cms` to force re-download.

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

See [plans/ROADMAP.md](plans/ROADMAP.md) for current status and open problems.
