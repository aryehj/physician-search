# Experiment: Plain-Language Condition Translator

## Status

- [x] Phase 1: Eval harness + gold profiles
- [ ] Phase 2: Deterministic translator (arm A)
- [ ] Phase 3: Local-LLM translator (arm B) + write report

## Context

Today the pipeline is hard-coded for piriformis syndrome. Condition-specific
inputs live in four places:

- `scripts/fetch_authors.py:27` — `SEARCH_QUERIES` (11 PubMed queries)
- `scripts/cms_db.py:35` — `RELEVANT_CMS_SPECIALTIES`
- `scripts/cms_db.py:48` — `RELEVANT_TAXONOMIES`
- `scripts/cms_db.py:68` — `TARGET_HCPCS` with weights
- `scripts/merge_and_rank.py:72,247` — `piriformis_injection_services` field

We want `uv run main.py --condition "tennis elbow"` to just work. The open
question: how to translate free-text into those inputs without a frontier
model — deterministic lookups, or a local small LLM on 8 GB Apple Silicon?

This plan is a **throwaway experiment**. The deliverable is a written
verdict in `eval/REPORT.md`, not production code. Pipeline integration is
out of scope — that's a follow-up plan, written with the experiment's
findings in hand.

## Goals

- A small scoring harness comparing `translate(term) -> ConditionProfile`
  implementations against hand-built gold profiles.
- Two implementations: deterministic (arm A) and local-LLM (arm B).
- `eval/REPORT.md` with metrics, qualitative review, and a recommendation.
- If both arms score poorly (hcpcs_f1 < 0.5 across the board), the
  report's recommendation is "pause and rethink" — do not force a winner.

---

## Phase 1: Eval harness + gold profiles

### Gold profiles

Build three hand-curated `ConditionProfile` JSON files under
`eval/gold/<slug>.json`, each with `pubmed_queries`, `hcpcs_weights`,
`cms_specialties`, `taxonomy_codes`, plus inline comments justifying picks.

1. **piriformis-syndrome** — ported from existing hard-coded constants.
2. **tennis-elbow** (lateral epicondylitis) — another MSK/procedural
   condition, different anatomy and specialty mix.
3. **high-blood-pressure** — deliberately off-distribution: a medication-
   managed chronic condition, not procedural. HCPCS codes will be E&M
   visits, labs, ambulatory BP monitoring (93784–93790), ECG. Specialties
   are internal medicine, cardiology, nephrology. This is a stress test:
   the existing procedure-volume pipeline is built around procedural
   conditions, so a translator that works well here suggests the
   architecture generalizes; one that fails here tells us where the
   abstraction breaks.

### Harness

`eval/harness.py` with:

- `load_gold() -> dict[str, ConditionProfile]`
- `score(predicted, gold) -> dict` returning two metrics:
  - `hcpcs_f1` — set F1 on code overlap (ignores weights)
  - `taxonomy_f1` — set F1 on taxonomy codes
- `run_arm(translate_fn) -> Report` calling `translate_fn` on each gold
  slug, scoring against gold.
- `print_report(report)` → markdown table with per-condition scores.
- `identity` anchor arm returning the gold profile as-is — confirms the
  scorer rates it at 1.0 before we trust it.

CMS specialties and PubMed queries get **qualitative review only** —
print predicted vs. gold side-by-side in the report for eyeballing.

### Files

- `eval/gold/piriformis-syndrome.json`
- `eval/gold/tennis-elbow.json`
- `eval/gold/high-blood-pressure.json`
- `eval/harness.py`
- `scripts/condition_profile.py` — `ConditionProfile` dataclass with
  `to_json`/`from_json`.

### Testing

`uv run eval/harness.py --arm identity` → all scores 1.0.

---

## Phase 2: Deterministic translator (arm A)

### Reference data

Vendor two CSVs into `scripts/reference/` on this branch:

- **CMS PFSRVU** procedure descriptions → `pfs_codes.csv` (`HCPCS`,
  `DESCRIPTION`). Public domain.
- **NUCC taxonomy** → `taxonomy.csv` (`Code`, `Classification`,
  `Specialization`, `Definition`).

No download-on-first-run logic. A roadmap entry will be added to revisit
this before any production use — vendored snapshots go stale.

CMS specialty list is queried from the existing `cms.duckdb` at runtime
(`SELECT DISTINCT specialty FROM provider_procedures`).

### Translator

`scripts/translator_deterministic.py`:

1. Normalize input (lowercase, strip punctuation).
2. Look up in `CONDITION_SYNONYMS` dict (hand-curated for the 3 gold
   conditions). Each entry: `aliases`, `anatomy_keywords`,
   `procedure_keywords`, `mesh_terms`, `specialty_hints`. Exact match
   first, then `rapidfuzz` token_set_ratio ≥ 85.
3. Score rows in `pfs_codes.csv` by keyword overlap: +10 for (anatomy ∧
   procedure), +3 for anatomy only, +1 for procedure only. Keep top 15
   codes with score ≥ 3; normalize weights to 1–10.
4. Score taxonomy rows against `Classification + Specialization +
   Definition` similarly. Keep all with score ≥ 1.
5. Substring-match `specialty_hints` against distinct CMS specialties.
6. Emit PubMed queries: `aliases + mesh_terms + (anatomy × procedure)`
   pairs, capped at 12.
7. Unknown term → raise. No open-world generalization in this arm.

### Files

- `scripts/translator_deterministic.py`
- `scripts/reference/pfs_codes.csv`, `scripts/reference/taxonomy.csv`
- `pyproject.toml` — add `rapidfuzz`

### Testing

`uv run eval/harness.py --arm deterministic` — iterate on
`CONDITION_SYNONYMS` until scores plateau. Record final numbers.

---

## Phase 3: Local-LLM translator (arm B) + write report

### Runtime

Ollama via HTTP (`http://localhost:11434/api/generate`). Default model
`qwen2.5:3b-instruct-q4_K_M` (~2 GB, fits 8 GB RAM). Fallbacks
documented: `llama3.2:3b`, `phi3:mini`.

### Translator

`scripts/translator_llm.py` exposing `translate(term) -> ConditionProfile`:

1. Probe Ollama `/api/tags` with 2 s timeout; clear error if unreachable.
2. Single prompt for a JSON object matching `CONDITION_SYNONYMS` shape.
   System prompt enforces JSON-only output with 1–2 worked examples.
3. `json.loads`; on failure, retry once, then raise.
4. Feed keywords through the **same deterministic scoring pipeline from
   Phase 2** (pfs_codes, taxonomy, CMS specialties, PubMed assembly).
   The LLM emits keywords; codes come from grounding against real data.

No caching.

### Report

Write `eval/REPORT.md`:

- Metrics table: per-condition `hcpcs_f1` and `taxonomy_f1`, per-arm.
- Qualitative side-by-side: predicted vs. gold PubMed queries and CMS
  specialties, per condition per arm.
- Per-condition commentary: where each arm succeeded/failed. Pay
  particular attention to high-blood-pressure — if both arms collapse
  there, that's a finding about the architecture, not just the
  translator.
- Recommendation: arm A, arm B, hybrid (A for seeded, B for fallback),
  or "pause and rethink" if both arms are below hcpcs_f1 0.5.

### Files

- `scripts/translator_llm.py`
- `eval/REPORT.md`

### Testing

```bash
brew install ollama && ollama pull qwen2.5:3b-instruct-q4_K_M
ollama serve &
uv run eval/harness.py --arm deterministic
uv run eval/harness.py --arm llm
```

---

## Notes

- **"Gold" here means opinionated human judgment**, not ground truth.
  The eval measures *agreement with the curator*, a reasonable proxy at
  this scale.
- **This branch is throwaway.** Don't invest in test suites, polish, or
  backwards-compat. The output is the report.
- **High blood pressure as a stress test.** The existing pipeline
  assumes procedural conditions. If neither arm produces a useful
  `ConditionProfile` for HTN, the report should note that productionizing
  plain-language input likely requires rethinking `find_by_procedures.py`
  and the HCPCS-weighted scoring model, not just the translator.
- **Out of scope.** UMLS/SNOMED, embedding rerankers, pipeline
  integration, download-on-first-run reference data.
