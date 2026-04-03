# Phase 2: Create `main.py` Orchestrator

**Prerequisite:** Phase 1 complete (scripts in `scripts/`, each has a `run()` function).

## Goal

Create `/Users/Shared/physician-search/main.py` that runs the full pipeline with one command, passing data in-memory between stages and writing intermediate files at each stage.

## CLI Interface

```
uv run main.py [options]
  --state IL        Filter by state (optional)
  --city Chicago    Filter by city (optional)
  --top 200         How many top-ranked to check against Anthem (default: 200)
```

## Import Mechanism

Scripts are in `scripts/` (not a Python package). Use `sys.path` manipulation:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from fetch_authors import run as fetch_authors_run
from lookup_npis import run as lookup_npis_run
from find_practice_colleagues import run as find_practice_colleagues_run
from find_by_procedures import run as find_by_procedures_run
from merge_and_rank import run as merge_and_rank_run
from merge_and_rank import compute_score  # needed for re-scoring in Stage 7
from check_anthem_network import run as check_anthem_network_run
```

## Dependency Block

Consolidate all dependencies from all scripts:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "lxml", "python-dotenv"]
# ///
```

## Pipeline Stages

### Stage 1: Fetch authors from PubMed

```python
articles, authors = fetch_authors_run()
save_json(articles, DATA_DIR / "articles.json")
save_json(authors, DATA_DIR / "authors.json")
```

### Stage 2: Look up NPI numbers

```python
physicians = lookup_npis_run(authors)
save_json(physicians, DATA_DIR / "physicians.json")
```

### Stage 3: Find practice colleagues

```python
colleagues = find_practice_colleagues_run(physicians, state=args.state)
save_json(colleagues, DATA_DIR / "practice_colleagues.json")
```

### Stage 4: Find by procedure volume

```python
published_npis = {p["npi"] for p in physicians if p.get("npi")}
procedure_physicians = find_by_procedures_run(
    state=args.state,
    city=args.city,
    published_npis=published_npis,
)
save_json(procedure_physicians, DATA_DIR / "procedure_physicians.json")
```

### Stage 5: Initial merge and rank (WITHOUT Anthem data)

```python
ranked = merge_and_rank_run(
    physicians=physicians,
    in_network=[],  # no in-network data yet
    procedures=procedure_physicians,
    colleagues=colleagues,
    state=args.state,
    city=args.city,
)
save_json(ranked, DATA_DIR / "ranked_physicians.json")
```

### Stage 6: Check top N against Anthem

```python
top_n = ranked[:args.top]

# TEMPORARY WORKAROUND (removed in Phase 3):
# merge_and_rank output uses first_name, but check_anthem_network
# expects fore_name for the FHIR name search.
for rec in top_n:
    if "fore_name" not in rec:
        rec["fore_name"] = rec.get("first_name", "")

in_network = check_anthem_network_run(top_n)
save_json(in_network, DATA_DIR / "in_network_physicians.json")
```

### Stage 7: Re-score with in-network data

This is the key new logic. After Anthem check, some records gain `in_anthem_network` and `accepting_new_patients` signals, which changes their score and potentially their rank.

```python
# Build lookup of in-network results by NPI
in_network_by_npi = {}
for rec in in_network:
    npi = rec.get("npi")
    if npi:
        in_network_by_npi[str(npi)] = rec

# Update ranked records with in-network signals
for rec in ranked:
    npi = str(rec.get("npi", ""))
    if npi in in_network_by_npi:
        anthem_data = in_network_by_npi[npi]
        rec["in_anthem_network"] = True
        rec["accepting_new_patients"] = anthem_data.get("accepting_new_patients", False)
        rec["anthem_networks"] = anthem_data.get("anthem_networks", [])
        rec["anthem_practitioner_id"] = anthem_data.get("anthem_practitioner_id", "")

# Recompute scores for ALL records
for rec in ranked:
    score, reasons = compute_score(rec)
    rec["score"] = round(score, 1)
    rec["reasons"] = reasons

# Re-sort by score
ranked.sort(key=lambda r: (
    -r["score"],
    -r.get("piriformis_injection_services", 0),
    -r.get("article_count", 0),
    r.get("last_name", ""),
))

# Re-assign ranks
for i, rec in enumerate(ranked, 1):
    rec["rank"] = i

# Save final results
save_json(ranked, DATA_DIR / "ranked_physicians.json")
```

**Edge cases handled:**
- Records checked but NOT found in Anthem: not in `in_network_by_npi`, so `in_anthem_network` stays `False`
- Records below the top-N cutoff: never checked, stay `False`
- `compute_score` is a pure function imported from `merge_and_rank` — safe to call independently

## Helper Function

```python
DATA_DIR = Path("data")

def save_json(data: list[dict], path: Path):
    """Write data to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Saved {path} ({len(data)} records)")
```

## Console Output

Print stage headers with `=` separators for visual clarity. At the end, print a summary:

```
PIPELINE COMPLETE
  Total ranked physicians: 1957
  In Anthem network: 15

  Top 10:
    #1  65.6  Agrawal, Divya [IN-NETWORK]
    #2  50.0  Shah, Sameer
    ...
```

## Important Notes

- `load_dotenv()` in `check_anthem_network.py` runs at import time (module level). This is fine — `.env` is at project root which is CWD.
- The `compute_score` import is critical — it MUST be a module-level function in `merge_and_rank.py` (not nested inside `run()`). Verify this during Phase 1.
- `DATA_DIR.mkdir(exist_ok=True)` should be called early in `main()`.

## Verification

1. `uv run main.py --help` — verify args parse correctly
2. `uv run main.py --state IL --top 10` — quick test (limits Anthem to 10 calls)
3. Verify `data/ranked_physicians.json` has `in_anthem_network` fields populated on some records
4. Verify intermediate files all exist: `ls data/*.json`
5. Compare final ranked output: in-network physicians should have higher scores than the initial Stage 5 ranking
