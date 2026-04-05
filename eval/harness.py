# /// script
# requires-python = ">=3.11"
# dependencies = ["duckdb", "rapidfuzz", "httpx"]
# ///
"""
Eval harness for plain-language condition translators.

Loads hand-curated gold ConditionProfiles, runs a `translate(term) -> profile`
callable against each, and scores predictions with set F1 on HCPCS codes and
taxonomy codes. Qualitative fields (CMS specialties, PubMed queries) are
printed side-by-side for eyeballing — no score.

Run:
    uv run eval/harness.py --arm identity
    uv run eval/harness.py --arm deterministic  # phase 2
    uv run eval/harness.py --arm llm            # phase 3
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Make scripts/ importable whether invoked from repo root or elsewhere.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from condition_profile import ConditionProfile  # noqa: E402

GOLD_DIR = Path(__file__).resolve().parent / "gold"

# Human-readable term each gold profile's slug represents. The translator is
# called with the term; scored against the gold profile.
GOLD_TERMS = {
    "piriformis-syndrome": "piriformis syndrome",
    "tennis-elbow": "tennis elbow",
    "carpal-tunnel-syndrome": "carpal tunnel",
    "rotator-cuff-tear": "rotator cuff tear",
    "high-blood-pressure": "high blood pressure",
    "type-2-diabetes": "type 2 diabetes",
    "migraine": "migraine",
    "cataract": "cataract",
    "breast-cancer": "breast cancer",
    "ulcer": "ulcer",
}


TranslateFn = Callable[[str], ConditionProfile]


@dataclass
class ConditionScore:
    slug: str
    term: str
    hcpcs_f1: float
    taxonomy_f1: float
    predicted: ConditionProfile
    gold: ConditionProfile


@dataclass
class Report:
    arm: str
    scores: list[ConditionScore] = field(default_factory=list)

    def mean_hcpcs_f1(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.hcpcs_f1 for s in self.scores) / len(self.scores)

    def mean_taxonomy_f1(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.taxonomy_f1 for s in self.scores) / len(self.scores)


def load_gold() -> dict[str, ConditionProfile]:
    profiles: dict[str, ConditionProfile] = {}
    for path in sorted(GOLD_DIR.glob("*.json")):
        profile = ConditionProfile.load(path)
        profiles[profile.slug] = profile
    return profiles


def _set_f1(predicted: set[str], gold: set[str]) -> float:
    if not predicted and not gold:
        return 1.0
    if not predicted or not gold:
        return 0.0
    tp = len(predicted & gold)
    if tp == 0:
        return 0.0
    precision = tp / len(predicted)
    recall = tp / len(gold)
    return 2 * precision * recall / (precision + recall)


def score(predicted: ConditionProfile, gold: ConditionProfile) -> dict:
    return {
        "hcpcs_f1": _set_f1(set(predicted.hcpcs_weights), set(gold.hcpcs_weights)),
        "taxonomy_f1": _set_f1(set(predicted.taxonomy_codes), set(gold.taxonomy_codes)),
    }


def run_arm(translate_fn: TranslateFn, arm_name: str) -> Report:
    gold = load_gold()
    report = Report(arm=arm_name)
    for slug, profile in gold.items():
        term = GOLD_TERMS.get(slug, slug.replace("-", " "))
        predicted = translate_fn(term)
        metrics = score(predicted, profile)
        report.scores.append(
            ConditionScore(
                slug=slug,
                term=term,
                hcpcs_f1=metrics["hcpcs_f1"],
                taxonomy_f1=metrics["taxonomy_f1"],
                predicted=predicted,
                gold=profile,
            )
        )
    return report


def _fmt_list(items, n=None):
    items = list(items)
    if n:
        items = items[:n]
    return ", ".join(items) if items else "(none)"


def print_report(report: Report) -> None:
    print(f"\n# Eval report — arm: {report.arm}\n")
    print("## Metrics\n")
    print("| condition | hcpcs_f1 | taxonomy_f1 |")
    print("|---|---|---|")
    for s in report.scores:
        print(f"| {s.slug} | {s.hcpcs_f1:.3f} | {s.taxonomy_f1:.3f} |")
    print(f"| **mean** | **{report.mean_hcpcs_f1():.3f}** | **{report.mean_taxonomy_f1():.3f}** |")

    print("\n## Qualitative side-by-side\n")
    for s in report.scores:
        print(f"### {s.slug}\n")
        print("**HCPCS (predicted):** " + _fmt_list(sorted(s.predicted.hcpcs_weights)))
        print("\n**HCPCS (gold):** " + _fmt_list(sorted(s.gold.hcpcs_weights)))
        print("\n**Taxonomy (predicted):** " + _fmt_list(sorted(s.predicted.taxonomy_codes)))
        print("\n**Taxonomy (gold):** " + _fmt_list(sorted(s.gold.taxonomy_codes)))
        print("\n**CMS specialties (predicted):** " + _fmt_list(s.predicted.cms_specialties))
        print("\n**CMS specialties (gold):** " + _fmt_list(s.gold.cms_specialties))
        print("\n**PubMed queries (predicted):** " + _fmt_list(s.predicted.pubmed_queries))
        print("\n**PubMed queries (gold):** " + _fmt_list(s.gold.pubmed_queries))
        print()


# ---------- Arms ----------

def identity_arm(term: str) -> ConditionProfile:
    """Anchor arm: returns the gold profile as-is. Should score 1.0 everywhere."""
    gold = load_gold()
    # Find by term match.
    for slug, term_text in GOLD_TERMS.items():
        if term_text == term:
            return gold[slug]
    raise KeyError(f"identity arm: no gold profile for term {term!r}")


def _load_arm(name: str) -> TranslateFn:
    if name == "identity":
        return identity_arm
    if name == "deterministic":
        from translator_deterministic import translate  # type: ignore
        return translate
    if name == "llm":
        from translator_llm import translate  # type: ignore
        return translate
    raise SystemExit(f"unknown arm: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", default="identity",
                        choices=["identity", "deterministic", "llm"])
    parser.add_argument("--llm-model", default=None,
                        help="ollama model tag (e.g. qwen2.5:3b-instruct-q4_K_M)")
    args = parser.parse_args()

    arm_label = args.arm
    if args.arm == "llm":
        import os
        if args.llm_model:
            os.environ["OLLAMA_MODEL"] = args.llm_model
        arm_label = f"llm ({os.environ.get('OLLAMA_MODEL', 'default')})"

    translate_fn = _load_arm(args.arm)
    report = run_arm(translate_fn, arm_label)
    print_report(report)


if __name__ == "__main__":
    main()
