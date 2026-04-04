# Architecture Decision Records

## ADR-001: Scripts live in `scripts/` and expose a `run()` function

**Date:** 2026-04-03
**Status:** Accepted

### Context

The project started as six standalone scripts at the project root, each a self-contained `main()` that read files, did work, and wrote files. Phase 2 will add a `main.py` orchestrator that chains all pipelines together without touching disk between stages, and Phase 3 will add re-scoring based on live Anthem data. Both require calling into the scripts programmatically rather than shelling out.

### Decision

Moved all six scripts into `scripts/` via `git mv`. Refactored each to extract a `run()` function containing the core logic (no file I/O), returning output data as Python objects. `main()` becomes a thin wrapper: parse CLI args, load files, call `run()`, write files.

Specific signatures:
- `fetch_authors.run() -> (articles, authors)`
- `lookup_npis.run(authors, query_all) -> physicians`
- `find_by_procedures.run(state, city, published_npis, min_score, top, url) -> enriched`
- `find_practice_colleagues.run(physicians, state, match_type, hospital_threshold) -> colleagues`
- `merge_and_rank.run(physicians, in_network, procedures, colleagues, ...) -> records`
- `check_anthem_network.run(physicians) -> in_network`

`apply_filters` in `merge_and_rank` was also refactored from accepting an `argparse.Namespace` to explicit keyword parameters, so it can be called by `main.py` without constructing a fake args object.

`DATA_DIR = Path("data")` remains CWD-relative (not `__file__`-relative) so both `uv run scripts/foo.py` from the project root and `import` from a project-root `main.py` resolve to the same `data/` directory.

### Consequences

- All six scripts remain fully functional as standalone CLIs — existing usage is unchanged except for the `scripts/` prefix.
- `main.py` (Phase 2) can `sys.path.insert(0, 'scripts')` and import `run()` from each module without subprocess overhead.
- Print statements stay in `run()` so progress feedback works whether called from CLI or from `main.py`.
- `compute_score` in `merge_and_rank` stays module-level (not nested in `run()`) so Phase 3 can import it directly for re-scoring.

## ADR-002: main.py orchestrator with two-pass scoring

**Date:** 2026-04-03
**Status:** Accepted

### Context

The pipeline needs to check top-ranked physicians against Anthem's network API, but ranking requires merge_and_rank to run first. Anthem data then changes scores (in-network gets a boost), so the final ranking differs from the initial one.

### Decision

`main.py` runs a 7-stage pipeline: Stages 1-4 gather data from three independent pipelines, Stage 5 does an initial merge/rank with `in_network=[]`, Stage 6 checks the top N against Anthem, and Stage 7 re-scores all records with the Anthem data and re-sorts. `compute_score` and `rank_sort_key` are imported from `merge_and_rank` so the scoring/sorting logic is defined in one place.

The `fore_name`/`first_name` field name mismatch between merge_and_rank output and check_anthem_network input is handled by a temporary workaround in main.py, to be resolved in Phase 3 with schema normalization.

### Consequences

- Two-pass scoring means `compute_score` runs twice on all records. Acceptable at current scale (~2K records).
- Stages 3 and 4 are independent and could be parallelized in a future optimization, but run sequentially for now.
- The ranked_physicians.json file is only written once (after Stage 7), not after the initial Stage 5 merge.
- The `fore_name` workaround is a known schema debt item tracked for Phase 3.

## ADR-003: DuckDB for CMS data, concurrent NPPES queries

**Date:** 2026-04-04
**Status:** Accepted

### Context

The pipeline had three performance bottlenecks: Stage 2 made ~1,000 serial NPPES API calls (~5 min), Stage 3 made dozens of serial NPPES zip+taxonomy queries (~2-3 min), and Stage 4 downloaded and scanned a ~300 MB CSV with ~10M rows in Python (~10 min). The CMS CSV and NPPES API return overlapping data (NPI, name, specialty, location), but each stage queried independently.

### Decision

1. **DuckDB as shared data store.** The CMS CSV is imported once into a DuckDB database (`data/cms/cms.duckdb`, ~50-80 MB compressed). A new shared module `scripts/cms_db.py` manages download, import, indexing, and provides query methods (`lookup_by_name`, `providers_in_zip`, `procedure_volume`). Stages 2, 3, and 4 all query this database instead of scanning CSV or making redundant API calls.

2. **Concurrent async NPPES queries.** All remaining NPPES API calls use `httpx.AsyncClient` with an `asyncio.Semaphore(10)` for concurrency control. A shared `batch_nppes()` function in `cms_db.py` handles this. NPPES is used as a fallback for authors not in CMS (Stage 2) and for street addresses not available in CMS data (Stage 3).

3. **Shared constants.** `RELEVANT_TAXONOMIES`, `RELEVANT_CMS_SPECIALTIES`, `TARGET_HCPCS`, and `TAXONOMY_SEARCH_TERMS` are defined once in `cms_db.py` and imported by other scripts, eliminating prior duplication.

4. **`--refresh-cms` flag.** Controls when the DuckDB database is rebuilt. Without it, the existing database is reused. The CMS CSV filename includes the data year, so new years get new downloads automatically; `--refresh-cms` forces a full rebuild.

### Consequences

- Stage 2 drops from ~5 min to ~30 sec, Stage 3 from ~2-3 min to ~30 sec, Stage 4 from ~10 min to ~1 sec. First run adds ~1-2 min for one-time CSV→DuckDB import.
- CMS data only covers Medicare billers. Younger physicians or those in purely private-pay practices won't appear in CMS lookups. The NPPES fallback in Stage 2 handles this, but CMS-matched physicians from Stage 2 lack street addresses (CMS only has city/state/zip). This reduces Stage 3's ability to do high-confidence address matching for those seeds.
- `duckdb` is now a required dependency for all pipeline scripts (added to inline `uv` metadata).
- The DuckDB file is ~50-80 MB vs ~300 MB for the raw CSV. Both are gitignored under `data/cms/`.

## ADR-004: Affiliation-based geographic validation for author-to-NPI matching

**Date:** 2026-04-04
**Status:** Accepted

### Context

The author-to-NPI matching in `lookup_npis.py` used pure name-based matching: CMS DB lookup on `last_name` exact + `first_name` prefix, with no consideration of PubMed affiliation data. This produced false positives:

- "Martin, Hal David" (hip surgeon in Dallas, TX) matched to NPI 1720647605, a Physician Assistant in Chicago — same name, completely different person.
- "Verma, Nishank" (physiatrist in Chandigarh, India) matched to Nikhil N. Verma (sports medicine at Rush, Chicago) — common surname, first-name prefix `N%` matched both.

These false matches propagated through the entire pipeline, inflating scores for wrong providers and attributing research expertise to people who didn't have it.

### Decision

Added three validation layers to both the CMS and NPPES matching phases in `lookup_npis.py`:

1. **First-name compatibility** (`_first_name_compatible`): Compares author and provider first names beyond prefix matching. Handles initials, abbreviations, and multi-word names, but rejects clearly different names (Nishank != Nikhil).

2. **Affiliation geographic validation** (`_affiliation_matches_location`): Extracts US state codes from PubMed affiliation strings (both abbreviations like ", TX " and full names like "Oklahoma"). Compares against provider's practice state. Returns `state_match`, `no_conflict`, or `state_mismatch`.

3. **Non-US country detection**: Recognizes ~40 country names in affiliations. Authors with only non-US affiliations are flagged as `state_mismatch` against any US provider.

Introduced a new match quality tier `affiliation_verified` (highest confidence) for matches where both specialty and geographic state align. Updated `merge_and_rank.py` `NPI_QUALITY_RANK` and scoring accordingly (+3 bonus for affiliation-verified).

### Consequences

- False positive matches like Martin and Verma are eliminated.
- Authors with no affiliations (empty list) still pass through as `no_conflict` — permissive by design.
- Authors with affiliations in multiple US states match providers in any of those states.
- The country detection list (~40 entries) is not exhaustive; obscure country names may slip through as `no_conflict` rather than `state_mismatch`. This is acceptable — false negatives (missing a valid match) are less harmful than false positives (wrong person).
- The `affiliation_verified` quality level is the new highest tier in `NPI_QUALITY_RANK`, above `relevant_specialty`.

## ADR-005: Generic procedure scoring in ranking layer

**Date:** 2026-04-04
**Status:** Accepted

### Context

The merge_and_rank scoring had a piriformis-specific weight (`piriformis_27096_per_service: 0.6`, capped at 50 services) separate from other procedures (`other_procedure_score_factor: 0.05`). This hardcoded condition-specific knowledge into the ranking layer, making the tool difficult to adapt to other medical conditions.

Meanwhile, `find_by_procedures.py` already encodes condition-specific procedure weights via `TARGET_HCPCS` in `cms_db.py` (e.g., 27096 gets 10x weight, trigger point procedures get 1-2x). The weighted score it produces already reflects condition-specific relevance.

### Decision

Replaced the two-part piriformis-specific scoring with a single generic `procedure_score_factor: 0.1` (per weighted point, capped at 300). The ranking layer now consumes `weighted_procedure_score` as an opaque number — all condition-specific weighting lives in `TARGET_HCPCS` in `cms_db.py`.

Also increased publication weights (base bonus of 10 pts for any publications, 5 pts/pub up from 3) and added multi-pipeline combination bonuses (published + procedures = +15, any 2 sources = +5, all 3 = +10).

### Consequences

- To adapt the tool to a different condition, only `cms_db.py` constants (search terms, HCPCS codes, taxonomy codes) need to change. The ranking layer works generically.
- The `piriformis_injection_services` field remains in the data records for reference but is no longer used in scoring.
- Published authors now reliably outrank non-published providers when other signals are similar (1 pub = 15 pts vs. relevant_specialty = 10 pts).
- Multi-pipeline corroboration is explicitly rewarded: a provider who publishes AND does high-volume procedures scores 20-25 points higher than the sum of those signals in isolation.

## ADR-006: "Published + practices" combo uses CMS presence, not specific procedure codes

**Date:** 2026-04-04
**Status:** Accepted

### Context

The `combo_published_and_procedures` bonus (+15 pts) required a provider to appear in both the publication pipeline AND the procedure pipeline (`find_by_procedures.py`). In practice this bonus never fired: zero NPI overlap existed between the two pipelines for piriformis syndrome. Investigation revealed the cause — published academic physicians (e.g., Nho at Rush) ARE in CMS billing data (10 rows, 80+ services), but they bill for different HCPCS codes (joint injections 20610, imaging, E&M visits) than the condition-specific `TARGET_HCPCS` codes the procedure pipeline filters on (27096, 20552, 64450, etc.).

The underlying insight: a physician who publishes on a condition and actively bills Medicare with a relevant specialty is almost certainly treating that condition, regardless of which specific procedure codes appear in their claims. Requiring exact HCPCS overlap is too narrow — it misses the most credible providers.

### Decision

Broadened the combo trigger from "publication source AND procedure source" to "publication source AND active practitioner," where active practitioner means either:
1. Found by the procedure pipeline with `weighted_procedure_score > 0`, OR
2. CMS-confirmed with `npi_match_quality` of `affiliation_verified` or `relevant_specialty` (meaning the provider was matched in Medicare billing data with a relevant specialty and, for affiliation_verified, geographic consistency with their publication affiliations)

Renamed the weight key from `combo_published_and_procedures` to `combo_published_and_practicing` and the reason string from "published + procedures" to "published + practices."

CMS data is a single annual snapshot (no per-row dates), so "active practitioner" means "billed Medicare in the most recent data year." The `--refresh-cms` flag ensures the latest year is used.

### Consequences

- The combo bonus now fires for published authors confirmed in CMS (e.g., Nho: 71 → 86 pts). This matches the intuitive ranking: a physician who researches AND treats a condition should outrank one who only does one or the other.
- Acceptable signal loss: a provider could have a relevant specialty and CMS presence without actually treating the specific condition. This is mitigated by the fact that they must also have publications on the condition — the combination of "publishes on X" + "bills Medicare as a relevant specialist" is a strong signal even without exact procedure code overlap.
- To adapt to another condition, no changes needed in this logic — the condition-specific filtering stays in `TARGET_HCPCS` and PubMed search terms, while "practices" remains a generic CMS-presence check.
- No recency filtering within the CMS data year is possible. A provider who billed in January but retired in December of the same data year would still qualify. The annual refresh cycle bounds the staleness to ~1-2 years.

## ADR-007: Author deduplication uses full first-name token, not first initial

**Date:** 2026-04-04
**Status:** Accepted

### Context

Author deduplication in `fetch_authors.py` keyed on `(last_name, first_initial)`, e.g. `verma|n`. This merged any authors sharing a last name and first initial into one record, conflating different people: "Nikhil N Verma" (orthopedic surgeon at Rush University, Chicago) was merged with "Nishank Verma" (physiatrist in Chandigarh, India). The merged author inherited both PMIDs and both affiliations, so downstream NPI matching attributed the Indian publication to the US physician. Analysis found 164 such false merges across the dataset, heavily concentrated in common surnames (Chen, Kim, Lee, Park, Zhang, etc.).

### Decision

Changed the dedup key from `(last_name_lower, first_initial)` to `(last_name_lower, first_name_token_lower)` where `first_name_token` is the first whitespace-delimited token of the fore name. Added Unicode accent normalization (`unicodedata.normalize("NFD")` with combining-mark stripping) so legitimate variants like "Moisés"/"Moises" and "Jérome"/"Jerome" still merge correctly.

### Consequences

- 164 previously-merged author pairs are now correctly separated. Author count increases from ~2,648 to ~2,812.
- Slight under-merging: an author listed as "D" on one paper and "Daniel" on another will no longer merge. This is acceptable — false separation is far less harmful than false conflation, and the initial-only case is uncommon for prolific authors.
- Publication counts become more accurate, which improves downstream ranking (publication bonus is 10 + 5×count, so a false extra pub was worth 5 points).
- Combined with the existing first-name compatibility check and affiliation-based geographic validation in `lookup_npis.py` (ADR-004), this provides defense in depth: dedup prevents conflation at the author level, and NPI matching prevents it at the provider level.
