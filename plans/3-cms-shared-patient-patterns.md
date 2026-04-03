# Plan 3: CMS Shared Patient Patterns

## Goal

Find physicians who share Medicare patients with our known published piriformis experts. If Dr. A (a published author we already identified) and Dr. B frequently co-manage the same patients, Dr. B likely treats similar conditions — even if they've never published.

## Data Source

**CMS Physician Shared Patient Patterns** — bulk CSV files published annually on `data.cms.gov`.

- Dataset: "Physician Shared Patient Patterns" (search `data.cms.gov` for it)
- Format: CSV with columns like `npi_1`, `npi_2`, `shared_count`, `same_day_count`
- Each row = a pair of providers who shared >= 11 Medicare patients in a year
- File size: large (several GB compressed). Multiple files split by "30-day" and "180-day" windows.
- Direct download links are on `data.cms.gov`; the 30-day file is the more clinically relevant one

**IMPORTANT — URL discovery:** CMS reorganizes `data.cms.gov` periodically and download URLs drift. The first step of the script MUST use a web search or the `data.cms.gov` catalog API to find the current download URL for the most recent year's 30-day file, rather than hardcoding a URL. Document the discovered URL and year in the script output. Provide a `--url` CLI arg as fallback for manual override if auto-discovery fails.

## Known Limitation

The CMS data has an **11-patient minimum** — provider pairs who shared fewer than 11 Medicare patients in a year are excluded for privacy. This means low-volume specialists and physicians who primarily see commercially-insured or younger patients may not appear at all. This is a structural limitation of the dataset, not something we can work around.

## Approach

### Script: `find_shared_patients.py`

Single standalone script with inline `uv` dependencies, matching project conventions.

**Step 0 — Discover download URL**

- Search `data.cms.gov` catalog/API for the most recent "Physician Shared Patient Patterns" dataset
- Try the CKAN-style catalog endpoint: `https://data.cms.gov/api/1/metastore/schemas/dataset/items` or search the site
- Look specifically for the **30-day** variant (more clinically relevant than 180-day)
- Extract the direct CSV/ZIP download URL
- Print and log the discovered URL and dataset year
- If auto-discovery fails, print an error with instructions to manually provide the URL via `--url` CLI arg

**Step 1 — Download the data**

- Fetch the discovered 30-day shared patient patterns CSV from `data.cms.gov`
- Store in `data/cms/` (create subdir). File is large; stream download, show progress.
- If file already exists locally, skip download.

**Step 2 — Load our known physician NPIs**

- Read `data/physicians.json`
- Extract the set of NPIs for physicians with `is_relevant_specialty: true`
- This is our "seed set" of ~306 published experts

**Step 3 — Scan the shared patient file**

- Stream-read the CSV line by line (do NOT load into memory — file is multi-GB)
- Parse the header row to find column indices by name (do NOT hardcode column positions — they may change between years)
- For each row: if `npi_1` OR `npi_2` is in our seed set, collect the *other* NPI and the `shared_count`
- Accumulate results: `{partner_npi: {shared_with: [list of seed NPIs], total_shared: N}}`
- Print progress every 1M rows during scan (the file is huge)

**Step 4 — Filter and enrich**

- Rank partner NPIs by total shared patient count (higher = stronger signal)
- For top candidates (e.g., top 200), query NPPES API to get name, specialty, address
- Filter to relevant specialties using the same `RELEVANT_TAXONOMIES` set from `lookup_npis.py`
- Filter to geographic area of interest (initially Cook County, IL)

**Step 5 — Output**

- Write `data/shared_patient_physicians.json` with same schema as `physicians.json` plus extra fields: `shared_patient_count`, `shared_with_npis` (list of seed NPIs they share patients with)
- Write `data/shared_patient_physicians.csv` for quick review

### Key Implementation Details

- Use `httpx` for download, `csv` stdlib for streaming reads
- Respect project conventions: inline `uv` script metadata, `httpx`, rate limiting on NPPES calls
- Add CLI args: `--skip-download` (reuse previously downloaded file), `--url` (manual download URL override), `--min-shared` (minimum shared patient count, default 20), `--state` filter
- Print progress every 1M rows during scan

### Rate Limits / Constraints

- CMS bulk download: no auth needed, no rate limit (just bandwidth)
- NPPES API: same ~3 req/sec as existing `lookup_npis.py`

## Verification

1. Run `uv run find_shared_patients.py` — should discover URL, download CMS file, scan it, query NPPES
2. Check `data/shared_patient_physicians.json` — should contain providers not in our original `physicians.json`
3. Spot-check: pick a result, verify on CMS data that they do share patients with a known expert
4. Cross-reference a few results with Google to sanity-check specialty relevance
5. Verify URL discovery worked (check script output for the logged URL and year)

## Open Questions

- Which year's file to use? Most recent available. The script should document which year it downloaded.
- Threshold for shared patient count? Start with >= 20 shared patients as minimum, adjustable via CLI arg.
