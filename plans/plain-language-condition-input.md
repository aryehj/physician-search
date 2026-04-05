# Experiment: Plain-Language Condition Translator

## Status

- [x] Phase 1: Eval harness + gold profiles (initial 3)
- [x] Phase 2a: Deterministic translator (arm A) — initial pass on 3-condition set
- [x] Phase 1b: Expand gold set to 10 conditions spanning distinct axes
- [x] Phase 2b: Re-tune arm A against the 10-condition set
- [ ] Phase 3: Local-LLM translator (arm B) + write report

## Arm A baseline (10 conditions)

| condition | hcpcs_f1 | taxonomy_f1 |
|---|---|---|
| ulcer | 0.414 | 0.320 |
| high-blood-pressure | 0.400 | 0.385 |
| type-2-diabetes | 0.312 | 0.296 |
| cataract | 0.308 | 0.571 |
| rotator-cuff-tear | 0.308 | 0.710 |
| breast-cancer | 0.267 | 0.345 |
| tennis-elbow | 0.231 | 0.296 |
| piriformis-syndrome | 0.200 | 0.278 |
| carpal-tunnel-syndrome | 0.160 | 0.545 |
| migraine | 0.154 | 0.600 |
| **mean** | **0.275** | **0.435** |

Ceiling behaviors, for arm B to be measured against:
- **HCPCS F1 caps at ~0.4** because consumer HCPCS descriptions don't mention condition-specific vocabulary — e.g. CPT `64721` "Release and/or relocation of hand nerve" never says "carpal" or "median", and every 20552 "Injection of trigger points" has no piriformis-specific anatomy. Set threshold change (base≥1 vs base≥3) has no effect: anatomy-matching rows already saturate top-15 for every condition.
- **Taxonomy F1 spreads 0.28–0.71** by specialty narrowness. Narrow-specialty conditions (cataract→ophth, rotator-cuff→ortho, migraine→neuro) score well; conditions with many overlapping specialty hints (piriformis, tennis-elbow, T2DM) dilute precision.
- **E&M codes (99202–99215) are never recovered.** They match only procedure vocab ("outpatient visit"), base=1, and get displaced from top-15 by every anatomy-matching row. Any condition where E&Ms are a significant fraction of gold (T2DM, migraine, HBP, ulcer) loses recall to this.
- **Ambiguous lay terms.** `breast cancer` arm A returns mostly 19xxx surgical codes, missing mammography/chemo/radiation; it collapses to surgical interpretation. `ulcer` arm A returns 43xxx EGD codes (peptic), matches gold — but would return the same for any GI-endoscopy condition, which is a precision risk not captured by this single-gold-interpretation eval.

## Why the expansion

Arm A scored hcpcs_f1 ≈ 0.27 and taxonomy_f1 ≈ 0.32 on 3 conditions. With
n=3, one stubborn condition (piriformis: gold codes whose consumer
descriptions contain no condition-specific anatomy) dominates the mean —
tuning becomes overfitting to one row, and arm-vs-arm differences are
noise-bound. Curating more gold profiles is cheaper than curating signal
out of a 3-row table. Lesson: simplify the *translator*, not the eval.

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

## Phase 1b: Expanded gold set (10 conditions)

The 3 initial conditions clustered on two axes (MSK-procedural,
chronic-medication). Expand to 10 spanning five axes, including two
deliberately vague lay terms that hide specialty/treatment complexity.

| # | slug | term | axis |
|---|------|------|------|
| 1 | piriformis-syndrome | "piriformis syndrome" | MSK, procedural, anatomically-specific |
| 2 | tennis-elbow | "tennis elbow" | MSK, procedural, anatomically-specific |
| 3 | carpal-tunnel-syndrome | "carpal tunnel" | MSK/neuro, procedural, cross-specialty |
| 4 | rotator-cuff-tear | "rotator cuff tear" | MSK, surgical, specialty-narrow |
| 5 | high-blood-pressure | "high blood pressure" | chronic, meds, E&M-heavy |
| 6 | type-2-diabetes | "type 2 diabetes" | chronic, meds+labs, endo/IM |
| 7 | migraine | "migraine" | neuro, mixed E&M + procedural (botox) |
| 8 | cataract | "cataract" | surgical, specialty-narrow (ophth) |
| 9 | **breast-cancer** | "breast cancer" | **ambiguous lay term** — spans screening (radiology), surgery (breast/gen-surg onc), medical oncology, radiation oncology, reconstruction (plastic) |
| 10 | **ulcer** | "ulcer" | **ambiguous lay term** — peptic (GI), diabetic foot (podiatry/endo/vasc), pressure (wound care), venous leg (vasc/derm); gold encodes the most common lay meaning (peptic) with notes on the others |

The two ambiguous terms are the real test: a good translator either
resolves to the most-likely meaning, returns a broad multi-specialty
profile, or raises an ambiguity signal. The gold profiles for these
commit to **one canonical interpretation** and the report discusses
what each arm does with the ambiguity.

### Deliverables

- Seven new `eval/gold/<slug>.json` profiles, same schema as existing,
  each with `_comments` documenting clinical rationale and (for breast
  cancer / ulcer) the ambiguity it hides.
- Extend `GOLD_TERMS` in `eval/harness.py`.
- Expand `CONDITION_SYNONYMS` in `translator_deterministic.py` to cover
  all 10 conditions before re-running arm A.

### Exit criteria

All 10 gold profiles load, `--arm identity` scores 1.0 across the
board, `--arm deterministic` runs without errors. Metrics are whatever
they are — Phase 2b tuning comes next.

---

## Phase 2b: Re-tune arm A on 10-condition set

Iterate `CONDITION_SYNONYMS` against the expanded eval. Record final
numbers per-condition. Specifically note which axes the keyword-overlap
approach handles well vs. poorly — that shapes the Phase 3 prompt
design for arm B and the report's recommendation.

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

Ollama via HTTP (`http://localhost:11434/api/generate`). Cross-platform
(Linux/Windows/Mac) — chosen over MLX because the deliverable has to be
runnable outside Apple Silicon.

### Model comparison

Three Qwen2.5-instruct models, differing only in parameter count. Same
family isolates size as the variable. Qwen2.5 was selected for strong
constrained-JSON output behavior with `format: "json"`.

| tier | model | ~RAM | host target |
|---|---|---|---|
| small | `qwen2.5:1.5b-instruct-q4_K_M` | ~1 GB | anywhere |
| mid | `qwen2.5:3b-instruct-q4_K_M` | ~2 GB | 8 GB host, comfortable alongside system |
| large | `qwen2.5:7b-instruct-q4_K_M` | ~4.5 GB | 16 GB host, comfortable alongside system |

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
# Install ollama (Mac: brew install ollama; Linux: see ollama.com/download)
# then pull all three models
ollama pull qwen2.5:1.5b-instruct-q4_K_M
ollama pull qwen2.5:3b-instruct-q4_K_M
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama serve &

# Run each arm against the 10-condition gold set, save output
uv run eval/harness.py --arm llm --llm-model qwen2.5:1.5b-instruct-q4_K_M > eval/results/llm-qwen25-1.5b.md
uv run eval/harness.py --arm llm --llm-model qwen2.5:3b-instruct-q4_K_M > eval/results/llm-qwen25-3b.md
uv run eval/harness.py --arm llm --llm-model qwen2.5:7b-instruct-q4_K_M > eval/results/llm-qwen25-7b.md

# Sanity-check a single translation without the harness:
OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M uv run scripts/translator_llm.py "tennis elbow"
```

The `--format json` mode constrains the Qwen tokenizer to valid JSON, so
the single-retry-then-raise path should rarely fire. Temperature is
pinned at 0 for reproducibility. No caching — each term makes a fresh
Ollama call, but n=10 conditions × 3 models = 30 calls is trivial.

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
