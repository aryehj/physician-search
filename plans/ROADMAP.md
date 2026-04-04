# Roadmap

## Completed

### 1. PubMed author extraction
Search PubMed for condition-related publications across multiple query terms. Extract all authors and affiliations, deduplicated to unique authors. Output: `data/authors.json`, `data/articles.json`.

### 2. NPI lookup
Match authors to NPIs using CMS DuckDB for fast name lookup, falling back to concurrent NPPES API queries for misses. Filters to relevant specialty taxonomy codes. Output: `data/physicians.csv`, `data/physicians.json`.

### 4. Procedure-volume pipeline (CMS Medicare data via DuckDB)
Find physicians who *perform* piriformis-relevant procedures at high volume, independent of publication history. CMS Medicare Provider Utilization data is downloaded once and imported into a DuckDB database (`data/cms/cms.duckdb`); procedure volume queries run in milliseconds via SQL. Filters to relevant HCPCS codes (27096 piriformis/sacroiliac injection weighted 10x; trigger point, nerve conduction, fluoroscopic guidance codes weighted 1-2x), ranks by weighted score. Optionally filters by state/city. Enriches via concurrent NPPES. Cross-references against Pipeline A published authors (`also_published` flag). Output: `data/procedure_physicians.json`, `data/procedure_physicians.csv`.

This addresses the core limitation of Pipeline A: competent treating physicians who never publish are now discoverable.

### 5. Practice-colleague discovery (CMS DuckDB + NPPES address matching)
Find physicians who share a practice location with known published experts. Takes seed physicians from Pipeline A, extracts their practice zip codes, uses CMS DuckDB for fast zip+specialty provider discovery, then fetches street addresses via concurrent NPPES queries for address matching. Three confidence tiers: same address (high confidence), same address at a probable hospital campus, and same zip + relevant specialty (noisier). Output: `data/practice_colleagues.json`, `data/practice_colleagues.csv`.

Partially addresses the gap noted in Open Problem 6: physicians who work alongside publishing experts but don't publish themselves are now discoverable.

### 6. Merge & rank across pipelines
Joins all three pipeline outputs (publications, procedure volume, practice colleagues) plus Anthem in-network data via NPI-keyed full outer join. Computes a composite priority score weighting piriformis injection volume (27096 code), publication count, in-network status, specialty relevance, and colleague proximity. Outputs a ranked call list. Supports `--state`, `--city`, `--min-score`, `--top`, `--in-network-only`, `--exclude-zip-only` flags. Output: `data/ranked_physicians.json`, `data/ranked_physicians.csv`.

### 3. Anthem in-network check
Query insurer's FHIR Provider Directory to check in-network status. Network affiliations extracted from DaVinci Plan-Net extensions on PractitionerRole resources.

**API notes:**
- Endpoint: `totalview.healthos.elevancehealth.com/resources/unregistered/api/v1/fhir/cms_mandate/mcd` (CMS-mandated, labeled Medicaid but returns commercial network data too)
- Auth: OAuth2 client credentials with Basic auth header (not form body)
- Practitioner search by `family`/`given` only (no `identifier`/NPI search) — must match NPI from returned results
- Network data lives in DaVinci extensions (`network-reference`, `newpatients`), not the standard FHIR `network` field
- Common network names seen: "Blue Choice Options PPO", "Participating Provider Option", "Blue Preferred PPO", "IL Blue Choice Select", "BCBS of Illinois PAR providers"

## In Progress

### 4. Identify specific network for user's plan
The API returns multiple network names per physician. Need to determine which network name corresponds to the user's specific plan to filter results more precisely. This may require checking insurance card/benefits portal or querying InsurancePlan resources.

## Open Problems

### 5. Improve match quality
Some results may be name collisions (e.g., Campbell with mostly out-of-state networks). Could improve by cross-referencing Anthem practice locations against NPPES practice addresses, or by filtering to physicians whose Anthem network list includes IL-specific networks.

### 6. Expand coverage beyond published authors
~~Addressed by Stage 4 (procedure-volume pipeline) and practice-colleague discovery.~~ CMS claims data finds high-volume practitioners who never publish; address matching finds colleagues of those who do. Remaining gaps: physicians who perform procedures but bill under a group NPI, or whose volume falls below Medicare reporting thresholds (typically <11 services/year). Hospital "find a doctor" pages could fill this further.

### 7. Make this usable by normal people. 
Normal people know MAYBE some words that are not medical terms of art for their diagnosis or suspicion. Maybe just symptoms. Assuming a plain language description of an actual diagnoses, someone should be able to run the full pipeline to return published authors and the whole bit. 