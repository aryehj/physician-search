# /// script
# requires-python = ">=3.11"
# dependencies = ["duckdb", "rapidfuzz"]
# ///
"""
Deterministic plain-language condition translator (arm A).

Looks up a user term in a hand-curated CONDITION_SYNONYMS table, then grounds
the keywords against vendored reference data (CMS PFS HCPCS descriptions,
NUCC taxonomy) and the live CMS DuckDB specialty list to emit a
ConditionProfile.

Scoring per reference row (tiered, with keyword-count tiebreakers):
    base 10 if row matches BOTH an anatomy and a procedure keyword
    base 3  if row matches only anatomy
    base 1  if row matches only procedure
    + (# distinct anatomy keywords matched) + (# distinct procedure
      keywords matched), so rows hitting more of the vocabulary rank
      above rows hitting only one keyword per category.

For HCPCS: keep the top 15 rows with base score >= 3 (so E&M-style
procedure-only rows are filtered out unless anatomy is also present).
For taxonomy: keep all rows with base score >= 1.

Unknown terms raise ValueError — no open-world generalization here.
That's arm B's job.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import duckdb
from rapidfuzz import fuzz

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from condition_profile import ConditionProfile  # noqa: E402

REFERENCE_DIR = Path(__file__).resolve().parent / "reference"
PFS_CSV = REFERENCE_DIR / "pfs_codes.csv"
TAXONOMY_CSV = REFERENCE_DIR / "taxonomy.csv"
CMS_DB_PATH = REPO_ROOT / "data" / "cms" / "cms.duckdb"

FUZZY_THRESHOLD = 85
MAX_HCPCS = 15
MAX_TAXONOMY = 20
MAX_PUBMED_QUERIES = 12

# Hand-curated synonym entries for the three gold conditions. Each entry
# captures the anatomy and procedure vocabulary the pipeline needs to
# recognize the condition in HCPCS descriptions, taxonomy definitions, and
# CMS specialty names, plus MeSH-ish terms for PubMed assembly.
CONDITION_SYNONYMS: dict[str, dict] = {
    "piriformis-syndrome": {
        "aliases": [
            "piriformis syndrome",
            "piriformis",
            "deep gluteal syndrome",
            "extraspinal sciatica",
            "piriformis muscle syndrome",
        ],
        "anatomy_keywords": [
            "piriformis", "sciatic", "gluteal", "hip", "sacroiliac",
            "lower spine", "peripheral nerve", "nerve", "muscle",
            "hip bone",
        ],
        "procedure_keywords": [
            "trigger point", "nerve conduction",
            "nerve block", "ultrasonic guidance",
            "fluoroscopic guidance", "facet joint",
            "botulinum", "needle placement",
            "steroid",
        ],
        "mesh_terms": [
            "piriformis muscle syndrome", "sciatica",
            "nerve compression syndromes",
        ],
        "specialty_hints": [
            "physical medicine", "neurology", "orthopedic",
            "neurological surgery", "sports medicine",
            "interventional radiology", "interventional pain",
            "osteopathic manipulative", "neuromuscular",
            "pain management", "anesthesiology",
        ],
    },
    "tennis-elbow": {
        "aliases": [
            "tennis elbow", "lateral epicondylitis",
            "lateral elbow tendinopathy",
            "extensor carpi radialis brevis tendinopathy",
            "lateral epicondyle tendinopathy",
        ],
        "anatomy_keywords": [
            "elbow", "tendon", "lateral", "epicondyle",
            "extensor", "forearm", "ligament",
        ],
        "procedure_keywords": [
            "injection", "incision", "tenotomy", "shock wave",
            "shockwave", "debridement", "arthroscopy", "endoscope",
            "platelet rich plasma", "imaging guidance",
            "ultrasonic guidance", "needle placement",
            "removal of", "repair",
        ],
        "mesh_terms": [
            "tennis elbow", "lateral epicondylitis",
            "tendinopathy", "elbow tendinopathy",
        ],
        "specialty_hints": [
            "orthopedic", "sports medicine", "physical medicine",
            "hand surgery", "interventional radiology",
        ],
    },
    "high-blood-pressure": {
        "aliases": [
            "high blood pressure", "hypertension",
            "essential hypertension", "htn", "elevated blood pressure",
        ],
        "anatomy_keywords": [
            "blood pressure", "blood", "hypertensive", "cardiac",
            "heart", "kidney", "renal", "electrocardiogram", "ecg",
            "cholesterol", "lipid", "glucose", "hemoglobin",
            "urinalysis",
        ],
        "procedure_keywords": [
            "ambulatory", "monitoring", "outpatient visit",
            "office visit", "blood test", "evaluation", "management",
            "routine electrocardiogram", "review", "interpretation",
            "scanning analysis", "recording",
        ],
        "mesh_terms": [
            "hypertension", "essential hypertension",
            "blood pressure", "antihypertensive agents",
        ],
        "specialty_hints": [
            "internal medicine", "family practice", "general practice",
            "cardiology", "nephrology", "endocrinology",
        ],
    },
    "carpal-tunnel-syndrome": {
        "aliases": [
            "carpal tunnel", "carpal tunnel syndrome",
            "median nerve entrapment", "median nerve compression",
        ],
        "anatomy_keywords": [
            "carpal", "wrist", "hand nerve", "median nerve",
            "median", "palm", "forearm",
        ],
        "procedure_keywords": [
            "release", "nerve conduction", "needle measurement",
            "electrical activity", "endoscope", "injection",
            "decompression",
        ],
        "mesh_terms": [
            "carpal tunnel syndrome", "median neuropathy",
            "nerve compression syndromes",
        ],
        "specialty_hints": [
            "hand surgery", "orthopedic", "orthopaedic", "neurology",
            "physical medicine", "plastic surgery", "neurological surgery",
            "neurosurgery", "neuromuscular",
        ],
    },
    "rotator-cuff-tear": {
        "aliases": [
            "rotator cuff tear", "rotator cuff", "rotator cuff injury",
            "torn rotator cuff", "supraspinatus tear",
            "shoulder tendon tear",
        ],
        "anatomy_keywords": [
            "rotator cuff", "shoulder", "shoulder joint", "shoulder tendon",
            "supraspinatus", "tendon", "bursa",
        ],
        "procedure_keywords": [
            "repair", "endoscope", "arthroscopy", "arthroscopic",
            "debridement", "removal", "injection", "arthrocentesis",
            "decompression", "shaving",
        ],
        "mesh_terms": [
            "rotator cuff injuries", "shoulder impingement syndrome",
            "tendinopathy",
        ],
        "specialty_hints": [
            "orthopedic", "orthopaedic", "sports medicine",
            "hand surgery", "physical medicine",
        ],
    },
    "type-2-diabetes": {
        "aliases": [
            "type 2 diabetes", "type ii diabetes", "diabetes",
            "diabetes mellitus", "t2dm", "adult onset diabetes",
            "non insulin dependent diabetes",
        ],
        "anatomy_keywords": [
            "glucose", "hemoglobin a1c", "hemoglobin", "insulin",
            "glycated", "blood glucose", "microalbumin",
            "creatinine", "lipid", "cholesterol", "pancreatic",
        ],
        "procedure_keywords": [
            "self-management training", "self management",
            "nutrition therapy", "nutrition management",
            "outpatient visit", "office visit", "blood test",
            "level", "monitoring", "prevention", "education",
        ],
        "mesh_terms": [
            "diabetes mellitus, type 2", "hyperglycemia",
            "insulin resistance", "glycemic control",
        ],
        "specialty_hints": [
            "endocrinology", "internal medicine", "family practice",
            "family medicine", "general practice", "nephrology",
            "ophthalmology", "podiatry", "podiatrist",
        ],
    },
    "migraine": {
        "aliases": [
            "migraine", "chronic migraine", "migraine headache",
            "episodic migraine", "migraine with aura",
        ],
        "anatomy_keywords": [
            "occipital", "trigeminal", "face nerve", "head nerve",
            "upper neck", "back of head", "facial", "nerve",
        ],
        "procedure_keywords": [
            "chemodenervation", "injection of chemical",
            "paralysis", "botulinumtoxin", "botulinum", "nerve block",
            "injection", "outpatient visit", "office visit",
        ],
        "mesh_terms": [
            "migraine disorders", "headache disorders",
            "botulinum toxins, type a", "calcitonin gene-related peptide",
        ],
        "specialty_hints": [
            "neurology", "pain management", "interventional pain",
            "pain medicine", "anesthesiology", "internal medicine",
            "family practice", "family medicine",
        ],
    },
    "cataract": {
        "aliases": [
            "cataract", "cataracts", "lens opacity",
            "age-related cataract", "nuclear sclerotic cataract",
        ],
        "anatomy_keywords": [
            "cataract", "lens", "intraocular lens", "prosthetic lens",
            "artificial lens", "lens capsule", "eye", "cornea",
        ],
        "procedure_keywords": [
            "removal", "insertion", "phacoemulsification",
            "exam of visual system", "complete exam", "implantation",
            "extraction", "ultrasound scan",
        ],
        "mesh_terms": [
            "cataract", "cataract extraction", "phacoemulsification",
            "lens implantation, intraocular",
        ],
        "specialty_hints": [
            "ophthalmology", "optometry", "optometrist",
        ],
    },
    "breast-cancer": {
        "aliases": [
            "breast cancer", "breast carcinoma",
            "breast malignancy", "breast neoplasm",
            "carcinoma of the breast",
        ],
        "anatomy_keywords": [
            "breast", "mammary", "mammography", "mammogram",
            "breast duct", "nipple", "axillary", "lymph node",
        ],
        "procedure_keywords": [
            "biopsy", "removal", "partial removal", "mastectomy",
            "lumpectomy", "radiation therapy", "chemotherapy",
            "screening mammography", "diagnostic mammography",
            "placement of locating device", "reconstruction",
            "administration of chemotherapy",
        ],
        "mesh_terms": [
            "breast neoplasms", "breast carcinoma",
            "mammography", "mastectomy",
        ],
        "specialty_hints": [
            "oncology", "medical oncology", "radiation oncology",
            "surgical oncology", "hematology", "radiology",
            "diagnostic radiology", "plastic surgery",
            "gynecological oncology", "general surgery",
            "obstetrics", "gynecology",
        ],
    },
    "ulcer": {
        "aliases": [
            "ulcer", "peptic ulcer", "peptic ulcer disease",
            "gastric ulcer", "duodenal ulcer", "stomach ulcer",
        ],
        "anatomy_keywords": [
            "stomach", "esophagus", "upper small bowel",
            "duodenal", "gastrointestinal", "gi tract",
            "helicobacter", "helicobacter pylori",
        ],
        "procedure_keywords": [
            "flexible endoscope", "endoscope", "diagnostic exam",
            "biopsy", "control of bleeding", "breath test",
            "stool", "antibody", "outpatient visit", "office visit",
            "injection",
        ],
        "mesh_terms": [
            "peptic ulcer", "stomach ulcer", "duodenal ulcer",
            "helicobacter infections", "helicobacter pylori",
        ],
        "specialty_hints": [
            "gastroenterology", "internal medicine",
            "family practice", "family medicine", "general practice",
        ],
    },
}


# ---------- Lookup ----------

def _normalize(term: str) -> str:
    return " ".join(term.lower().strip().replace("-", " ").split())


def _find_entry(term: str) -> tuple[str, dict]:
    norm = _normalize(term)
    # Exact alias match first.
    for slug, entry in CONDITION_SYNONYMS.items():
        for alias in entry["aliases"]:
            if _normalize(alias) == norm:
                return slug, entry
    # Fuzzy match on aliases.
    best_slug: str | None = None
    best_entry: dict | None = None
    best_score = 0.0
    for slug, entry in CONDITION_SYNONYMS.items():
        for alias in entry["aliases"]:
            s = fuzz.token_set_ratio(norm, _normalize(alias))
            if s > best_score:
                best_score = s
                best_slug = slug
                best_entry = entry
    if best_score >= FUZZY_THRESHOLD and best_slug and best_entry:
        return best_slug, best_entry
    raise ValueError(
        f"deterministic translator: no synonym entry for {term!r} "
        f"(best fuzzy match score {best_score:.0f} < {FUZZY_THRESHOLD})"
    )


# ---------- Scoring ----------

def _row_score(text: str, anatomy: list[str], procedure: list[str]) -> tuple[int, int]:
    """Return (base_score, refined_score). base is tiered 10/3/1/0;
    refined adds keyword match counts as a tiebreaker."""
    t = text.lower()
    a_hits = sum(1 for kw in anatomy if kw.lower() in t)
    p_hits = sum(1 for kw in procedure if kw.lower() in t)
    if a_hits and p_hits:
        base = 10
    elif a_hits:
        base = 3
    elif p_hits:
        base = 1
    else:
        base = 0
    refined = base + a_hits + p_hits
    return base, refined


def _score_hcpcs(entry: dict) -> dict[str, int]:
    scored: list[tuple[int, int, str]] = []  # (refined, base, code)
    with open(PFS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            base, refined = _row_score(
                row["DESCRIPTION"],
                entry["anatomy_keywords"],
                entry["procedure_keywords"],
            )
            if base >= 1:
                scored.append((refined, base, row["HCPCS"]))
    # Sort by refined score, then base; anatomy-matching rows outrank
    # procedure-only rows, so E&M codes only make the cut if there's
    # nothing more specific to displace them.
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    top = scored[:MAX_HCPCS]
    if not top:
        return {}
    # Normalize refined scores to the 1-10 range.
    max_s = max(s for s, _, _ in top)
    min_s = min(s for s, _, _ in top)
    out: dict[str, int] = {}
    for refined, _, code in top:
        if max_s == min_s:
            w = 10
        else:
            w = round(1 + 9 * (refined - min_s) / (max_s - min_s))
        out[code] = w
    return out


def _score_taxonomy(entry: dict) -> list[str]:
    """Score taxonomy rows by specialty_hints (not anatomy/procedure).
    Taxonomy codes represent provider specialties, so specialty-level
    vocabulary is the appropriate match axis. Classification gets double
    weight since it's the canonical specialty name."""
    scored: list[tuple[int, str]] = []
    hints = [h.lower() for h in entry["specialty_hints"]]
    with open(TAXONOMY_CSV, newline="") as f:
        for row in csv.DictReader(f):
            classification = row.get("Classification", "").lower()
            specialization = row.get("Specialization", "").lower()
            definition = row.get("Definition", "").lower()
            score = 0
            for h in hints:
                if h in classification:
                    score += 3
                if h in specialization:
                    score += 2
                if h in definition:
                    score += 1
            if score >= 1:
                scored.append((score, row["Code"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [code for _, code in scored[:MAX_TAXONOMY]]


def _match_cms_specialties(entry: dict) -> list[str]:
    try:
        conn = duckdb.connect(str(CMS_DB_PATH), read_only=True)
    except Exception:
        # DB not available (e.g. in a fresh checkout); fail soft to [].
        return []
    try:
        rows = conn.execute(
            "SELECT DISTINCT specialty FROM cms ORDER BY specialty"
        ).fetchall()
    finally:
        conn.close()
    specialties = [r[0] for r in rows if r[0]]
    out: list[str] = []
    for sp in specialties:
        low = sp.lower()
        if any(hint.lower() in low for hint in entry["specialty_hints"]):
            out.append(sp)
    return out


def _build_pubmed_queries(entry: dict) -> list[str]:
    seen: set[str] = set()
    queries: list[str] = []

    def add(q: str) -> None:
        qn = q.strip()
        if qn and qn.lower() not in seen:
            seen.add(qn.lower())
            queries.append(qn)

    for alias in entry["aliases"]:
        add(alias)
    for mesh in entry["mesh_terms"]:
        add(mesh)
    # anatomy × procedure cross product, capped.
    for a in entry["anatomy_keywords"]:
        for p in entry["procedure_keywords"]:
            if len(queries) >= MAX_PUBMED_QUERIES:
                break
            add(f"{a} {p}")
        if len(queries) >= MAX_PUBMED_QUERIES:
            break
    return queries[:MAX_PUBMED_QUERIES]


# ---------- Public API ----------

def translate(term: str) -> ConditionProfile:
    slug, entry = _find_entry(term)
    return ConditionProfile(
        slug=slug,
        pubmed_queries=_build_pubmed_queries(entry),
        hcpcs_weights=_score_hcpcs(entry),
        cms_specialties=_match_cms_specialties(entry),
        taxonomy_codes=_score_taxonomy(entry),
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("term", help="plain-language condition term")
    args = parser.parse_args()
    profile = translate(args.term)
    print(profile.to_json())
