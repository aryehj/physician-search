# Phase 1: Move Scripts to `scripts/` and Extract `run()` Functions

## Goal

Move all 6 scripts into a `scripts/` directory and refactor each to expose a `run()` function that accepts input data as parameters and returns output data. The existing `main()` becomes a thin wrapper handling CLI args, file I/O, and calling `run()`.

## Step 1: Move files with git

```bash
mkdir -p scripts
git mv fetch_authors.py scripts/fetch_authors.py
git mv lookup_npis.py scripts/lookup_npis.py
git mv find_by_procedures.py scripts/find_by_procedures.py
git mv find_practice_colleagues.py scripts/find_practice_colleagues.py
git mv merge_and_rank.py scripts/merge_and_rank.py
git mv check_anthem_network.py scripts/check_anthem_network.py
```

Do the `git mv` first, THEN apply refactoring edits in the new locations.

## Step 2: Refactor Pattern

Every script follows the same pattern. The transformation is:

**Before:**
```python
def main():
    # parse CLI args
    # read input files
    # do work
    # write output files

if __name__ == "__main__":
    main()
```

**After:**
```python
def run(input_data, ...options) -> output_data:
    # do work (no file I/O)
    return results

def main():
    # parse CLI args
    # read input files
    results = run(input_data, ...options)
    # write output files

if __name__ == "__main__":
    main()
```

Keep ALL existing constants, helper functions, imports, and `# /// script` dependency blocks unchanged. Don't deduplicate anything across scripts.

## Step 3: Script-by-script refactoring

### 3a. `scripts/fetch_authors.py`

**`run()` signature:**
```python
def run() -> tuple[list[dict], list[dict]]:
    """Run PubMed fetch pipeline. Returns (articles, authors)."""
```

No input parameters — this script searches PubMed from scratch.

**What moves from `main()` into `run()`:**
- All the PubMed search logic (searching PMIDs, fetching XML, parsing, deduplicating)
- The print statements for progress
- Return `(all_articles, authors)` at the end

**What stays in `main()`:**
- `DATA_DIR.mkdir(exist_ok=True)`
- Calling `run()`
- Writing `articles.json` and `authors.json` to disk

### 3b. `scripts/lookup_npis.py`

**`run()` signature:**
```python
def run(authors: list[dict], query_all: bool = False) -> list[dict]:
    """Look up NPI numbers for authors. Returns list of physician dicts."""
```

**What moves from `main()` into `run()`:**
- The US-affiliation filtering logic (or `query_all` bypass)
- The NPPES query loop over candidates
- Building physician records
- Summary printing
- Return `physicians` list

**What stays in `main()`:**
- `"--all" in sys.argv` parsing
- Loading `data/authors.json`
- Calling `run(authors, query_all)`
- Writing `physicians.json` and `physicians.csv`

### 3c. `scripts/find_by_procedures.py`

**`run()` signature:**
```python
def run(
    state: str | None = None,
    city: str | None = None,
    published_npis: set[str] | None = None,
    min_score: float = 10.0,
    top: int = 500,
    url: str | None = None,
) -> list[dict]:
    """Find physicians by CMS procedure volume. Returns enriched list."""
```

**What moves from `main()` into `run()`:**
- CMS URL discovery and download
- CSV scanning
- Filtering and ranking
- NPPES enrichment
- If `published_npis is None`, call `load_published_npis()` as fallback (for standalone use). If caller passes an empty set, treat as "no cross-reference".
- Keep `DATA_DIR.mkdir(exist_ok=True)` and `CMS_DIR.mkdir(exist_ok=True)` inside `run()` because CMS download needs the directory
- Return the enriched provider list

**What stays in `main()`:**
- argparse setup
- Calling `run()` with parsed args
- Writing `procedure_physicians.json` and `.csv`

### 3d. `scripts/find_practice_colleagues.py`

**`run()` signature:**
```python
def run(
    physicians: list[dict],
    state: str | None = None,
    match_type: str = "both",
    hospital_threshold: int = 20,
) -> list[dict]:
    """Find practice colleagues of seed physicians. Returns colleague list."""
```

**What moves from `main()` into `run()`:**
- Seed physician filtering (relevant specialty + has NPI)
- Zip extraction from seed physicians
- NPPES queries by zip
- Address matching logic
- Confidence tier assignment
- Return colleagues list

**What stays in `main()`:**
- argparse setup
- Loading `data/physicians.json`
- Calling `run(physicians, ...)`
- Writing `practice_colleagues.json` and `.csv`

### 3e. `scripts/merge_and_rank.py`

**`run()` signature:**
```python
def run(
    physicians: list[dict],
    in_network: list[dict],
    procedures: list[dict],
    colleagues: list[dict],
    state: str | None = None,
    city: str | None = None,
    min_score: float = 1.0,
    top: int | None = None,
    in_network_only: bool = False,
    exclude_zip_only: bool = False,
) -> list[dict]:
    """Merge pipelines and produce ranked list. Returns ranked records."""
```

**Additional change — refactor `apply_filters`:**

Current `apply_filters` takes an `args` namespace object. Change it to accept explicit keyword parameters:

```python
def apply_filters(
    records: list[dict],
    state: str | None = None,
    city: str | None = None,
    min_score: float = 0.0,
    top: int | None = None,
    in_network_only: bool = False,
    exclude_zip_only: bool = False,
) -> list[dict]:
```

**What moves from `main()` into `run()`:**
- Calling `build_merged_index()`
- Score computation loop
- Sorting
- Calling `apply_filters()` with explicit params
- Rank assignment
- Name building
- `print_summary()` call
- Return the ranked list

**What stays in `main()`:**
- argparse setup
- Loading 4 JSON files via `load_json()`
- Calling `run(...)`
- Writing `ranked_physicians.json` and `.csv`

**Important:** `compute_score` must remain a module-level function (not nested inside `run()`), because `main.py` will import it directly for re-scoring in Phase 3.

### 3f. `scripts/check_anthem_network.py`

**`run()` signature (Phase 1 version — will be updated in Phase 3):**
```python
def run(physicians: list[dict]) -> list[dict]:
    """Check physicians against Anthem directory. Returns enriched in-network list."""
```

**What moves from `main()` into `run()`:**
- OAuth token acquisition
- The loop over physicians querying Anthem FHIR
- Record enrichment with Anthem fields
- Summary printing
- Return `in_network` list

**What stays in `main()`:**
- Env var validation (check for missing vars, `sys.exit` if missing)
- Loading `data/physicians.json`
- Cook County filtering (this is the standalone behavior)
- Calling `run(cook_county_physicians)`
- Writing `in_network_physicians.json` and `.csv`
- The `--probe` flag handling

**Note:** `load_dotenv()` stays at module level. The `COOK_COUNTY_CITIES` set stays as a module-level constant.

## Step 4: Update `CLAUDE.md`

Update all script paths from `fetch_authors.py` to `scripts/fetch_authors.py`, etc. Update the Running section examples:

```bash
# Pipeline A
uv run scripts/fetch_authors.py
uv run scripts/lookup_npis.py
uv run scripts/check_anthem_network.py

# Pipeline B
uv run scripts/find_by_procedures.py --state IL --city Chicago

# Pipeline C
uv run scripts/find_practice_colleagues.py --state IL
```

## Important Notes

- `DATA_DIR = Path("data")` uses relative paths resolved against CWD. Both standalone (`uv run scripts/foo.py` from project root) and import from `main.py` (at project root) resolve correctly. Do NOT change to `__file__`-relative paths.
- `uv run scripts/fetch_authors.py` works — `uv` reads `# /// script` blocks regardless of path.
- Keep all print statements in `run()` for progress feedback.

## Verification

1. Each script is importable:
   ```bash
   python3 -c "import sys; sys.path.insert(0, 'scripts'); from fetch_authors import run; print('ok')"
   # Repeat for all 6 scripts
   ```
2. Each script still runs standalone (test with short-running ones):
   ```bash
   uv run scripts/merge_and_rank.py --state IL --exclude-zip-only  # fastest test, reads local files only
   ```
3. No scripts remain at project root: `ls *.py` should show nothing (until Phase 2).
