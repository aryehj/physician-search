# Plan 1: CMS Provider Utilization & Procedure Volume

## Goal

Find physicians who frequently perform piriformis-relevant procedures, regardless of whether they publish. A doctor who bills 50 piriformis injections per year is experienced — publication history is irrelevant.

## Data Source

**CMS Medicare Provider Utilization and Payment Data** — published annually on `data.cms.gov`.

- Dataset: "Medicare Provider Utilization and Payment Data: Physician and Other Suppliers"
- Format: CSV, one row per (NPI, HCPCS code, place of service) combination
- Includes: NPI, provider name, credentials, specialty, HCPCS code, HCPCS description, number of services, number of beneficiaries, average payment
- File size: large (~2-3 GB compressed per year)
- No auth required

**IMPORTANT — URL discovery:** CMS reorganizes `data.cms.gov` periodically and download URLs drift. The first step of the script MUST use a web search or the `data.cms.gov` catalog API to find the current download URL for the most recent year's file, rather than hardcoding a URL. Document the discovered URL and year in the script output.

## Relevant CPT/HCPCS Codes

These are the procedure codes most relevant to piriformis syndrome diagnosis and treatment:

| Code | Description | Relevance | Weight |
|------|-------------|-----------|--------|
| 27096 | Injection procedure for sacroiliac joint / piriformis muscle under imaging | Very direct — specifically includes piriformis | **10** |
| 20552 | Injection(s); single or multiple trigger point(s), 1 or 2 muscle(s) | Direct — piriformis trigger point injection | 2 |
| 20553 | Injection(s); single or multiple trigger point(s), 3 or more muscles | Direct — multiple trigger point injections | 2 |
| 64450 | Injection, anesthetic agent; other peripheral nerve or branch | Sciatic nerve block near piriformis | 1 |
| 64640 | Destruction by neurolytic agent; other peripheral nerve or branch | Neurolysis for chronic piriformis cases | 1 |
| 95907-95913 | Nerve conduction studies (various) | Diagnostic — used to evaluate sciatic involvement | 1 |
| 64493 | Injection(s), paravertebral facet joint (lumbar/sacral) | Adjacent — often done in differential diagnosis | 1 |
| 76942 | Ultrasound guidance for needle placement | Often paired with piriformis injections | 1 |
| 77003 | Fluoroscopic guidance for needle placement | Often paired with piriformis injections | 1 |

**Weight rationale:** Code 27096 is the only truly piriformis-specific code (though shared with sacroiliac joint injection). It gets 10x weight because it is the primary signal. The other codes are general musculoskeletal/pain procedures — useful as supporting evidence but extremely noisy on their own. A physician with high 27096 volume and moderate trigger point volume is a much stronger candidate than one with only high trigger point volume (which could be a general pain practice doing shoulder/back trigger points).

## Approach

### Script: `find_by_procedures.py`

**Step 0 — Discover download URL**

- Search `data.cms.gov` catalog/API for the most recent "Medicare Provider Utilization and Payment Data: Physician and Other Suppliers" dataset
- Try the CKAN-style catalog endpoint: `https://data.cms.gov/api/1/metastore/schemas/dataset/items` or search the site
- Extract the direct CSV download URL
- Print and log the discovered URL and dataset year
- If auto-discovery fails, print an error with instructions to manually provide the URL via `--url` CLI arg

**Step 1 — Download the data**

- Fetch the discovered CSV from `data.cms.gov`
- Store in `data/cms/`. Stream download with progress. Skip if exists.

**Step 2 — Define target codes**

- Hardcode the HCPCS codes above in a dict with the weights shown in the table
- The weighted score = sum of (service_count * code_weight) across all relevant codes

**Step 3 — Scan the utilization file**

- Stream-read CSV line by line
- **Pre-filter optimization:** Provider specialty is already in the CMS data. Skip rows whose specialty doesn't match our relevant set before checking HCPCS codes — this dramatically reduces processing time.
- For matching rows: if HCPCS code is in our target set, collect the NPI and accumulate:
  - `{npi: {codes: {code: {services: N, beneficiaries: N}}, total_weighted_score: float}}`

**Step 4 — Filter and rank**

- Rank by `total_weighted_score`
- For top candidates, check if NPI is already in our `physicians.json` (flag as "also published")
- Query NPPES for name, specialty, address for NPIs not already in our data
- Filter to relevant specialties and geographic area

**Step 5 — Output**

- Write `data/procedure_physicians.json` — same base schema as `physicians.json` plus:
  - `procedure_volume`: dict of code -> count
  - `weighted_score`: float
  - `also_published`: bool (whether they're in our PubMed-derived set)
- Write `data/procedure_physicians.csv`

### Key Implementation Details

- Match project conventions: inline `uv` deps, `httpx`, streaming reads
- The utilization CSV columns vary slightly by year — parse header row, find columns by name
- Add CLI args: `--min-score` (default 10), `--state` filter, `--county` filter, `--url` (manual override if auto-discovery fails)
- Print running stats during scan

## Verification

1. Run `uv run find_by_procedures.py --state IL`
2. Check output files exist and contain reasonable data
3. Verify that some high-scoring providers are already in our published-author set (sanity check)
4. Verify that new providers not in our set appear and have relevant specialties
5. Spot-check a few NPIs on the NPPES website to confirm they're real providers in relevant fields
6. Verify that high-scoring results are dominated by 27096 volume, not just generic trigger point codes

## Open Questions

- Code 27096 is shared between sacroiliac joint and piriformis injection — can't distinguish from billing data alone. Accept as noise; the specificity is still high enough given the specialty filter.
- Should we also look at ICD-10 diagnosis codes (G57.0 sciatic nerve lesion, M79.3 panniculitis)? The utilization file doesn't include diagnosis codes — that's in a different CMS dataset (not publicly available at provider level). So no, stick to HCPCS.
