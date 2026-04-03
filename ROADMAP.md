# Roadmap

## Completed

### 1. PubMed author extraction
Search PubMed for piriformis-related publications across 11 query terms. Extract all authors and affiliations from 702 articles, deduplicated to 2,647 unique authors. Output: `data/authors.json`, `data/articles.json`.

### 2. NPI lookup
Query the NPPES registry for US-based authors. Match against relevant specialty taxonomy codes (PM&R, pain medicine, neurology, orthopedic surgery, neurosurgery, anesthesiology/pain). Output: `data/physicians.csv`, `data/physicians.json` — 1,904 records, 306 with relevant specialties.

### 3. Anthem in-network check (Cook County, IL)
Filter physicians to Cook County, IL (29 with NPIs), then query Anthem's FHIR Provider Directory to check in-network status. 10 of 29 found in directory, all accepting new patients. Network affiliations extracted from DaVinci Plan-Net extensions on PractitionerRole resources.

**API notes:**
- Endpoint: `totalview.healthos.elevancehealth.com/resources/unregistered/api/v1/fhir/cms_mandate/mcd` (CMS-mandated, labeled Medicaid but returns commercial network data too)
- Auth: OAuth2 client credentials with Basic auth header (not form body)
- Practitioner search by `family`/`given` only (no `identifier`/NPI search) — must match NPI from returned results
- Network data lives in DaVinci extensions (`network-reference`, `newpatients`), not the standard FHIR `network` field
- Common network names seen: "Blue Choice Options PPO", "Participating Provider Option", "Blue Preferred PPO", "IL Blue Choice Select", "BCBS of Illinois PAR providers"

## In Progress

### 4. Identify specific network for ESI PPO plan
The API returns multiple network names per physician. Need to determine which network name corresponds to the user's specific ESI PPO plan to filter results more precisely. This may require checking insurance card/benefits portal or querying InsurancePlan resources.

## Open Problems

### 5. Improve match quality
Some results may be name collisions (e.g., Campbell with mostly out-of-state networks). Could improve by cross-referencing Anthem practice locations against NPPES practice addresses, or by filtering to physicians whose Anthem network list includes IL-specific networks.

### 6. Expanding beyond published authors
The PubMed pipeline finds people who *write about* piriformis syndrome. But a competent treating physician may never publish a paper — they may instead:

- Practice alongside a published expert and absorb that expertise through daily collaboration
- Have trained under or completed a fellowship with a known piriformis/deep-gluteal specialist
- Work in a department or practice group that has a published track record, even if they personally haven't authored papers

These practitioners are invisible to a publication search but may be exactly the right physician to see. The signal is indirect: shared practice addresses, overlapping institutional affiliations, residency/fellowship program connections, or referral network proximity to known experts.

This is a harder data problem. Possible inputs include practice group rosters (from NPI practice addresses or hospital "find a doctor" pages), residency program alumni lists, and co-billing patterns in claims data. We don't yet have a solution — just the recognition that publication authorship is a useful but incomplete proxy for clinical competence in a specific condition.
