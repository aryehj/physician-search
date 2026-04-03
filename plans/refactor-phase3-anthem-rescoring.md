# Phase 3: Flexible Anthem Check + Cleanup

**Prerequisite:** Phases 1 and 2 complete.

## Goal

Update `check_anthem_network.py`'s `run()` to handle physician records from ANY pipeline (not just Pipeline A), and remove the `fore_name` workaround from `main.py`.

## Problem

After the merge, records use `first_name`, `city`, `state`. But `check_anthem_network.run()` was written expecting Pipeline A records with `fore_name`, `practice_city`, `practice_state`. The Phase 2 workaround patches `fore_name` onto records before calling `run()`, but this is fragile.

## Step 1: Update `run()` in `scripts/check_anthem_network.py`

### Field name handling

Inside `run()`, where it reads physician names for the FHIR search, change from:

```python
first_name = phys.get("fore_name", "")
```

to:

```python
first_name = phys.get("fore_name") or phys.get("first_name", "")
```

This handles both Pipeline A records (which have `fore_name`) and merged records (which have `first_name`).

### Move env var validation into `run()`

Currently env var validation is in `main()`. Move it into `run()` so that callers (including `main.py`) get a clear error. Use `raise RuntimeError(...)` instead of `sys.exit()`:

```python
def run(physicians: list[dict]) -> list[dict]:
    # Validate env vars
    missing = [
        var for var in [
            "ANTHEM_CLIENT_ID", "ANTHEM_CLIENT_SECRET",
            "ANTHEM_ACCESS_TOKEN_URL", "ANTHEM_PROVIDER_DIRECTORY_URL",
        ]
        if not os.environ.get(var)
    ]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
    
    # Filter to records with NPI
    physicians_with_npi = [p for p in physicians if p.get("npi")]
    print(f"Checking {len(physicians_with_npi)} physicians against Anthem directory")
    
    # ... rest of function ...
```

### NPI type safety

The merged records may have NPI as string or int. Ensure consistent comparison:

```python
npi = str(phys["npi"])
```

## Step 2: Update `main()` in `scripts/check_anthem_network.py`

The standalone `main()` keeps Cook County filtering for backward compatibility. Remove the env var validation from `main()` (it's now in `run()`). Wrap the `run()` call in try/except to catch RuntimeError and print a friendly message:

```python
def main():
    physicians_path = DATA_DIR / "physicians.json"
    if not physicians_path.exists():
        print("Error: data/physicians.json not found.")
        sys.exit(1)

    with open(physicians_path) as f:
        physicians = json.load(f)

    cook_county = [
        p for p in physicians
        if p.get("practice_state") == "IL"
        and p.get("practice_city", "").upper() in COOK_COUNTY_CITIES
        and p.get("npi")
    ]
    print(f"Filtered to {len(cook_county)} in Cook County, IL with NPIs")

    try:
        in_network = run(cook_county)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # ... save JSON/CSV as before ...
```

## Step 3: Remove `fore_name` workaround from `main.py`

In `main.py` Stage 6, delete these lines:

```python
# REMOVE THIS BLOCK:
for rec in top_n:
    if "fore_name" not in rec:
        rec["fore_name"] = rec.get("first_name", "")
```

The call simplifies to:

```python
top_n = ranked[:args.top]
in_network = check_anthem_network_run(top_n)
```

## Step 4: Update `CLAUDE.md`

Update the Architecture section to reflect:
- Scripts are in `scripts/`, each exposes a `run()` function
- `main.py` orchestrates the full pipeline
- Anthem check runs on top-N merged results from all pipelines
- Update the Running section to show `uv run main.py` as the primary command

Update the Running section:

```bash
# Full pipeline
uv run main.py                                    # all defaults
uv run main.py --state IL --city Chicago --top 100

# Individual stages (standalone)
uv run scripts/fetch_authors.py
uv run scripts/lookup_npis.py
uv run scripts/check_anthem_network.py
uv run scripts/find_by_procedures.py --state IL
uv run scripts/find_practice_colleagues.py --state IL
uv run scripts/merge_and_rank.py --state IL --exclude-zip-only
```

## Step 5: Update `plans/ROADMAP.md`

Add to Completed section:

```markdown
### 7. Pipeline orchestrator (`main.py`)
Single command runs the full pipeline: fetch authors → NPI lookup → practice colleagues → procedure volume → merge & rank → Anthem network check (top N) → re-score. Anthem check now runs on top-N merged results from all pipelines, not just Pipeline A Cook County physicians. Supports `--state`, `--city`, `--top` flags.
```

## Verification

1. Standalone still works:
   ```bash
   uv run scripts/check_anthem_network.py
   ```
   Should filter to Cook County and check Pipeline A physicians as before.

2. Full pipeline:
   ```bash
   uv run main.py --top 10
   ```
   Verify:
   - Stage 5 produces rankings WITHOUT `in_anthem_network`
   - Stage 6 checks 10 providers against Anthem (these may come from any pipeline)
   - Stage 7 re-scores: providers found in Anthem should have scores ~20 pts higher than initial
   - Final `ranked_physicians.json` has `in_anthem_network: true` on found providers
   - Ranks are reassigned after re-sort

3. Compare runs:
   ```bash
   uv run main.py --top 5   # check fewer
   uv run main.py --top 50  # check more
   ```
   The `--top 50` run should find a superset of in-network physicians.
