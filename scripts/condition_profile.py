# /// script
# requires-python = ">=3.11"
# ///
"""
ConditionProfile dataclass — the output shape of a plain-language translator.

A ConditionProfile captures everything the pipeline needs to know about a
medical condition to drive PubMed search, CMS procedure-volume scoring, and
specialty/taxonomy filtering.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ConditionProfile:
    slug: str
    pubmed_queries: list[str] = field(default_factory=list)
    hcpcs_weights: dict[str, int] = field(default_factory=dict)
    cms_specialties: list[str] = field(default_factory=list)
    taxonomy_codes: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "ConditionProfile":
        data = json.loads(text)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "ConditionProfile":
        # hcpcs_weights keys must be strings; coerce ints to str just in case
        weights = {str(k): int(v) for k, v in data.get("hcpcs_weights", {}).items()}
        return cls(
            slug=data["slug"],
            pubmed_queries=list(data.get("pubmed_queries", [])),
            hcpcs_weights=weights,
            cms_specialties=list(data.get("cms_specialties", [])),
            taxonomy_codes=list(data.get("taxonomy_codes", [])),
        )

    @classmethod
    def load(cls, path: Path) -> "ConditionProfile":
        return cls.from_json(Path(path).read_text())
