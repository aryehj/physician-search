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
