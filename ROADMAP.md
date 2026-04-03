# Roadmap

## Completed

### 1. PubMed author extraction
Search PubMed for piriformis-related publications across 11 query terms. Extract all authors and affiliations from 702 articles, deduplicated to 2,647 unique authors. Output: `data/authors.json`, `data/articles.json`.

### 2. NPI lookup
Query the NPPES registry for US-based authors. Match against relevant specialty taxonomy codes (PM&R, pain medicine, neurology, orthopedic surgery, neurosurgery, anesthesiology/pain). Output: `data/physicians.csv`, `data/physicians.json` — 1,904 records, 306 with relevant specialties.

## In Progress

### 3. Manual spot-check against Anthem BCBS
Search a handful of high-signal physician names on [findcare.anthem.com](https://findcare.anthem.com) to validate:
- Are published piriformis authors actually findable in the Anthem directory?
- Does searching by NPI work, or only by name/location?
- What plan-specific information is needed to get accurate in-network results?
- How much noise is there (e.g., same-name mismatches)?

This step informs how to approach automation.

## Next Decision

### 4. Automated insurance cross-reference via Anthem FHIR API

**API details (researched 2026-04-03):**

Anthem exposes a CMS-mandated Provider Directory API (FHIR R4, DaVinci PDEX Plan Net IG 1.1.0) at `totalview.healthos.elevancehealth.com`. Key resources: Practitioner, PractitionerRole (specialty, network, location refs), Organization, Location, InsurancePlan. Supports `_include` for efficient joined queries.

- **Registration:** Free at `anthem.com/developers/provider-directory-api-request` — application submitted, pending approval. OAuth 2.0 client credentials flow.
- **Sandbox:** `sbx.totalview.healthos.elevancehealth.com/registration/sandbox/login` — may be accessible before production credentials arrive.
- **Brand endpoints:** Each plan (Anthem BCBS, Anthem Blue Cross CA, Wellpoint, UniCare, etc.) has its own slug under `/resources/registered/{Brand}/api/v1/fhir`.
- **Key query:** `PractitionerRole?specialty={NUCC_code}&_include=PractitionerRole:practitioner,PractitionerRole:location` — returns in-network providers with name, NPI, address in one call.
- **Unregistered (public) endpoints** exist for Medicaid (`/resources/unregistered/api/v1/fhir/cms_mandate/mcd/`) — metadata works but data queries currently return 500.

**Plan:** Once credentials arrive, write a third pipeline script to cross-reference our 306 specialty-matched NPIs against Anthem's in-network directory for the patient's specific plan.

## Open Problems

### 5. Expanding beyond published authors
The PubMed pipeline finds people who *write about* piriformis syndrome. But a competent treating physician may never publish a paper — they may instead:

- Practice alongside a published expert and absorb that expertise through daily collaboration
- Have trained under or completed a fellowship with a known piriformis/deep-gluteal specialist
- Work in a department or practice group that has a published track record, even if they personally haven't authored papers

These practitioners are invisible to a publication search but may be exactly the right physician to see. The signal is indirect: shared practice addresses, overlapping institutional affiliations, residency/fellowship program connections, or referral network proximity to known experts.

This is a harder data problem. Possible inputs include practice group rosters (from NPI practice addresses or hospital "find a doctor" pages), residency program alumni lists, and co-billing patterns in claims data. We don't yet have a solution — just the recognition that publication authorship is a useful but incomplete proxy for clinical competence in a specific condition.
