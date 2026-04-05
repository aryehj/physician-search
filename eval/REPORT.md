# Plain-Language Condition Translator: Experiment Report

**Date:** 2026-04-05
**Branch:** supersearch (throwaway)
**Scope:** Compare a deterministic keyword-lookup translator (arm A) vs.
three local-LLM translators (arm B, Qwen2.5 at 1.5B / 3B / 7B) on a
10-condition gold set. Deliverable: a recommendation for whether to
build on either arm, or rethink the approach.

---

## Summary metrics (mean F1 across 10 conditions)

| arm | HCPCS F1 | taxonomy F1 |
|---|---|---|
| **A — deterministic** | **0.275** | **0.435** |
| B — qwen2.5:1.5b | 0.144 | 0.257 |
| B — qwen2.5:3b | 0.129 | 0.317 |
| B — qwen2.5:7b | 0.169 | 0.334 |
| B — meditron:7b (medical-specialized) | 0.160 | 0.315 |

**Arm A beats all four LLM variants on both metrics.** More parameters
help modestly on taxonomy (1.5B→7B: 0.257→0.334) but HCPCS F1 stays
stuck in the 0.13–0.17 range regardless of model size. The 3B model is
*worse* on HCPCS than the 1.5B model — we think because it generates
longer keyword lists that drag in more spurious matches, though we
didn't formally measure this.

**Meditron:7b (medical-specialized, Llama2 base) landed between
Qwen-3B and Qwen-7B — i.e. medical-domain training didn't help.**
Meditron's one genuine win was high-blood-pressure (HCPCS F1 0.229),
where it emitted keywords that matched the ABPM codes (93784–93790)
that no Qwen variant recovered. That's the kind of "the doctor knows
which labs/monitors match this disease" inference we hoped medical
specialization would unlock. It didn't generalize: Meditron still
scored 0 on cataract, migraine, and T2D, collapsing the same way
Qwen did (cataract → retinal codes 67xxx instead of lens codes
66xxx). Caveat: Meditron required grammar-constrained decoding
against an explicit JSON schema to produce the correct output shape
at all; with only `format: "json"` it returned a canned medical-QA
response (`{"name": "AI", "age": 25, "gender": "female"}`). That's
itself a note about medical-specialized models: they are tuned for
QA/dialogue, not pipeline-shaped structured output.

**Plan's "pause and rethink" rule fires.** The plan committed to
recommending pause-and-rethink if both arms scored `hcpcs_f1 < 0.5`.
Arm A peaks at 0.414 on a single condition and averages 0.275; no LLM
arm beats 0.17 average. The scoring architecture is the problem, not
the translator.

---

## Per-condition breakdown

HCPCS F1:

| condition | arm A | qwen-1.5B | qwen-3B | qwen-7B | meditron-7B | gap (A − best B) |
|---|---|---|---|---|---|---|
| ulcer | **0.414** | 0.000 | 0.069 | 0.000 | 0.069 | +0.35 |
| high-blood-pressure | **0.400** | 0.000 | 0.000 | 0.000 | 0.229 | +0.17 |
| type-2-diabetes | **0.312** | 0.000 | 0.000 | 0.000 | 0.000 | +0.31 |
| cataract | **0.308** | 0.154 | 0.000 | 0.154 | 0.000 | +0.15 |
| rotator-cuff-tear | 0.308 | 0.154 | 0.308 | 0.308 | **0.308** | 0 |
| breast-cancer | 0.267 | **0.400** | 0.267 | 0.267 | 0.267 | −0.13 |
| tennis-elbow | 0.231 | **0.385** | **0.385** | **0.385** | **0.385** | −0.15 |
| piriformis-syndrome | 0.200 | **0.267** | **0.267** | **0.267** | **0.267** | −0.07 |
| carpal-tunnel-syndrome | 0.160 | 0.080 | 0.000 | 0.160 | 0.080 | 0 |
| migraine | 0.154 | 0.000 | 0.000 | 0.154 | 0.000 | 0 |

Taxonomy F1:

| condition | arm A | qwen-1.5B | qwen-3B | qwen-7B | meditron-7B |
|---|---|---|---|---|---|
| rotator-cuff-tear | **0.710** | 0.452 | 0.452 | 0.516 | 0.583 |
| migraine | **0.600** | 0.200 | 0.200 | 0.200 | 0.200 |
| cataract | 0.571 | 0.750 | 0.750 | **0.778** | 0.750 |
| carpal-tunnel-syndrome | **0.545** | 0.182 | 0.242 | 0.242 | 0.242 |
| piriformis-syndrome | 0.278 | **0.333** | **0.333** | **0.333** | **0.333** |
| tennis-elbow | 0.296 | 0.296 | 0.296 | 0.296 | 0.296 |
| breast-cancer | 0.345 | 0.207 | **0.357** | **0.357** | 0.207 |
| ulcer | **0.320** | 0.000 | 0.160 | 0.160 | 0.160 |
| high-blood-pressure | **0.385** | 0.000 | 0.231 | 0.308 | 0.231 |
| type-2-diabetes | **0.296** | 0.148 | 0.148 | 0.148 | 0.148 |

---

## Why arm A wins: vocabulary alignment, not medical knowledge

The scoring pipeline grades both arms the same way: keyword lists are
substring-matched against `pfs_codes.csv` descriptions (for HCPCS),
NUCC `Classification+Specialization+Definition` (for taxonomy), and
CMS specialty names (for specialties). Both arms are grounded against
the same reference data, so the only thing that varies is the
**keywords themselves**.

Arm A's human curator *read `pfs_codes.csv`* and hand-picked keywords
that textually match the consumer-friendly CMS descriptions. E.g. for
piriformis syndrome, the curator knew to include `"nerve conduction"`
(verbatim in code 95907: "Nerve conduction, 1-2 studies") and
`"trigger point"` (verbatim in 20552: "Injection of trigger points,
1-2 muscles"). The LLM knows the **medical concepts** but emits
semantically equivalent vocabulary that isn't in the corpus:

- **Ulcer (canonical: peptic):** Qwen-7B emits `"stomach ulcer"`,
  `"intestinal ulcer"`, `"mucosal ulcer"`, `"bed sore"`, `"pressure
  ulcer"`. The gold keyword list uses `"flexible endoscope"`,
  `"helicobacter"`, `"biopsy"` — the actual text of EGD code
  descriptions. The 7B model's keywords match 0 of the gold HCPCS
  codes. (Also notably: 7B surfaced the ulcer ambiguity across peptic,
  pressure, and venous meanings — more on that below.)
- **High blood pressure:** Qwen-7B emits `"artery monitoring"`,
  `"artery angioplasty"`, `"artery stent"` and ends up matching AV
  fistula creation codes (36810–36830), which *are* adjacent to HTN
  via dialysis but are the wrong specialty for the query. No LLM arm
  emits `"hemoglobin a1c"` or `"outpatient visit"` — the actual text
  of the gold HCPCS rows.
- **Carpal tunnel:** Arm A keyword list includes `"nerve conduction"`
  and `"needle measurement"` (straight from NCS/EMG descriptions).
  Qwen doesn't emit those, so misses 95860/95886/95905 entirely.

**Conclusion: we're measuring keyword-text alignment, not medical
reasoning.** A human with a text editor beats an LLM at picking words
that a corpus contains, which is not an interesting contest. The
architecture is wrong.

---

## What the LLMs did well

**Narrow-specialty conditions where taxonomy definitions use
clinical vocabulary.** Qwen-7B cataract taxonomy F1 = 0.778 (beats
arm A's 0.571) because the model correctly identifies ophthalmology
sub-specialties from semantic knowledge, and NUCC definitions contain
enough ophthalmology vocabulary for the match to land. Same story for
breast-cancer taxonomy (0.357 vs arm A's 0.345).

**Ambiguity surfacing.** The lay-term stress tests produced the most
interesting qualitative behavior:

- **Ulcer:** 1.5B resolved to *pressure/wound* ulcer (dermatology,
  vascular); 3B resolved to *peptic* (GI, matching gold); 7B emitted
  keywords for *both* peptic and pressure/wound meanings — returning
  a multi-specialty output that scores worse on a single-gold eval
  but is arguably what a human user would want. None of the arms
  produced an explicit "this term is ambiguous" signal; the 7B
  behavior is the closest thing we got.
- **Breast cancer:** All LLMs collapsed to the diagnostic/biopsy arc
  (19081–19100 image-guided biopsies) and missed screening
  mammography + chemo/radiation codes. Arm A had the same collapse.
  The stress test succeeded at showing that neither arm handles the
  full disease arc.

**Tennis elbow, piriformis, rotator cuff** — LLMs tie or slightly
beat arm A on HCPCS F1 (+0.07 to +0.15), because the medical names
here (`"epicondyle"`, `"rotator cuff"`, `"sciatic"`) survive in CMS's
simplified descriptions. This is the one domain where LLMs plausibly
win with the current scoring architecture.

---

## Failure-mode inventory

Four classes of failure affect both arms, but hit LLMs harder:

1. **E&M codes are systematically unrecoverable.** 99202–99215
   descriptions contain only procedure-category vocabulary
   (`"outpatient visit"`, `"established patient"`) — no anatomy. Base
   score = 1 (procedure-only), top-15 cutoff displaces them. Arm A
   knows this and doesn't try; LLMs don't and pay the recall penalty
   for chronic conditions (HBP, T2D, migraine) where E&M codes are
   half the gold set.

2. **Lab codes are semantically distant from disease names.** HBP
   gold includes 80053 CMP, 80061 lipid, 83036 A1C. None of these
   descriptions contain "blood pressure" or "hypertension". The LLM
   would have to make the inference "HTN → end-organ monitoring →
   labs" and emit specific lab names. Qwen-7B doesn't; neither does
   arm A directly — arm A's HBP gold match on 83036 works because
   `"hemoglobin"` is in its keyword list.

3. **Ambiguous lay terms degrade precision, not recall.** All LLMs
   produced too-broad keyword sets for "ulcer" and "breast cancer"
   that pulled in adjacent-but-wrong specialties. Larger models were
   more ambiguity-aware but scored worse as a result.

4. **CPT codes with stripped-down consumer descriptions.** CMS's
   plain-English descriptions drop surgical terms of art that LLMs
   reach for. Code 64721 ("Release and/or relocation of hand nerve")
   says nothing about "median" or "carpal tunnel"; the LLM emits
   `"median nerve"`, `"carpal tunnel release"`, matches nothing.

---

## Sidebar: we tested a narrow, unrealistic input distribution

Partway through writing this report we asked: are we measuring the
right thing, or are our *input terms* themselves a bad assumption?
Our 10 gold terms are all diagnosis-named ("piriformis syndrome",
"carpal tunnel", "type 2 diabetes"). The literature says real
patients don't search that way:

- **Patients search by symptoms, not diagnoses.** An ED-population
  study (Cooper et al., *AEM* 2017) found **61.7% searched by
  symptoms**, 40.6% by diagnosis. Our gold set tests only the minority
  case.
- **Patient self-diagnosis is often wrong.** In the same study, among
  patients who *did* search by a specific diagnosis name, only **29%**
  received that diagnosis from the ED. A production translator needs
  to tolerate input that is *plausibly-but-incorrectly* self-diagnosed.
- **"Diagnostic medical circumlocutory queries"** is the formal
  research term for "butt pain that shoots down my leg" in place of
  "piriformis syndrome". There is existing HCI/IR literature on this
  translation problem (Stanton et al., 2014).
- **A comprehensive lay-↔-clinical vocabulary already exists.** The
  Consumer Health Vocabulary (Zeng & Tse, *JAMIA* 2006) is a formal
  UMLS-linked ontology of lay health terms; the current BioPortal
  release has ~115,645 classes. Our `CONDITION_SYNONYMS` with 10
  hand-curated entries is a toy reinvention of a tool that exists at
  scale. If we productionize any version of arm A, CHV should be the
  source for alias expansion — not a hand-maintained dict.

This doesn't invalidate the primary Phase 3 finding (keyword-overlap
scoring hits a ceiling regardless of input realism). But it does
reframe the question: *before* picking a scoring architecture, we
should decide what input distribution the system is for.

---

## Recommendation: pause and rethink

**Do not productionize either arm as-is.** The scoring architecture
— keyword-substring overlap on a fixed corpus — is the binding
constraint, and neither arm breaks through its ceiling.

Three directions worth exploring, in rough order of expected leverage:

1. **Dense retrieval instead of keyword overlap.** Embed each HCPCS
   description once (e.g. with a small sentence-transformer), embed
   the condition term + a short LLM-generated summary at query time,
   take top-k nearest descriptions. This lets the LLM's semantic
   knowledge drive matching without requiring vocabulary to align.
   We'd keep the same `ConditionProfile` output shape and the same
   gold eval — just swap the scoring pipeline.

2. **Richer reference data.** The consumer descriptions CMS uses are
   an intentional dumbing-down of CPT long descriptors. The AMA's
   long descriptors (licensed) or the CMS RVU file's medium
   descriptors would both contain more terms-of-art. This alone
   might raise arm A's ceiling by 0.1–0.2.

3. **Explicit ambiguity handling.** "Breast cancer" and "ulcer"
   aren't single conditions — they're disease areas. A
   production-shaped translator should emit a multi-profile output
   ("peptic ulcer OR pressure ulcer OR venous ulcer — which?") and
   let the pipeline query each. The 7B ulcer output already does
   this unintentionally; making it intentional changes the output
   schema.

4. **Realistic input distribution.** (See sidebar.) Rebuild the gold
   set around symptom-based queries and CHV-sourced lay paraphrases
   — e.g. "sharp pain in my butt when I sit" alongside "piriformis
   syndrome", "sugar" alongside "type 2 diabetes", "stomach ulcer"
   alongside "peptic ulcer disease". Use CHV (via UMLS) as the source
   of lay-term expansions instead of hand-curating them. This is
   arguably a prerequisite to directions 1–3, because the right
   scoring architecture depends on whether the input is a diagnosis
   name or a symptom paraphrase.

**Out of scope for this experiment:** the expanded plan would need
a new ADR and probably a fresh eval design (retrieval metrics ≠ F1
on code sets). This report closes out the current throwaway branch.

---

## Minor findings

- **Runtime cost of arm B is trivial.** 10 conditions × 4 models ran
  in ~2–3 min each on local Apple Silicon.
- **Grammar-constrained JSON decoding matters for non-Qwen models.**
  Qwen2.5 produced schema-conformant JSON with just
  `format: "json"` (valid-JSON constraint only). Meditron under the
  same flag returned a canned `{"name": "AI", "age": 25, "gender":
  "female"}` — a training-distribution JSON response unrelated to the
  prompt. Switching Ollama's `format` field from `"json"` to a full
  JSON schema object forced all models to emit exactly our five keys
  via grammar-constrained decoding, after which Meditron produced
  sensible medical values. Takeaway: for pipeline-shaped structured
  output, pass a JSON schema, not just `"json"`.
- **Arm A is fast too.** Each `translate()` call is a linear scan of
  a 9K-row CSV + a 900-row CSV + a DuckDB `SELECT DISTINCT`.
  Sub-second end-to-end.
- **`--llm-model` flag worked cleanly.** Passing the model via env
  var from the harness keeps the `translate(term) -> ConditionProfile`
  interface stable across arms.

## Files produced by this experiment

- `scripts/condition_profile.py` — output shape
- `scripts/translator_deterministic.py` — arm A
- `scripts/translator_llm.py` — arm B
- `scripts/reference/pfs_codes.csv`, `scripts/reference/taxonomy.csv` — vendored reference data
- `eval/gold/*.json` — 10 hand-curated condition profiles
- `eval/harness.py` — scoring harness
- `eval/results/llm-qwen25-{1.5b,3b,7b}.md` — raw per-arm output
- `eval/REPORT.md` — this file
