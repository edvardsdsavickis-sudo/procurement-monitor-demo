from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

from procurement_monitor.models import KeywordRule, MatchResult, Tender, canonical_text

def _split(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split("|") if item.strip())


def _bool(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "on"}


def rule_from_mapping(row: dict[str, str]) -> KeywordRule:
    def get(*names: str) -> str:
        for name in names:
            value = row.get(name)
            if value is not None:
                return str(value).strip()
        return ""

    weight_text = get("weight") or "20"
    try:
        weight = max(0, min(100, int(float(weight_text))))
    except ValueError:
        weight = 20

    return KeywordRule(
        rule_id=get("id") or get("keyword_lv"),
        category=get("category"),
        keyword_lv=get("keyword_lv"),
        keyword_en=get("keyword_en"),
        variants=_split(get("variants")),
        cpv_codes=_split(get("cpv_codes")),
        negative_terms=_split(get("negative_terms")),
        weight=weight,
        enabled=_bool(get("enabled") or "true"),
    )


def load_keyword_csv(path: Path) -> list[KeywordRule]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [rule_from_mapping(row) for row in csv.DictReader(handle)]


def _normalize_pattern(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^\w*]+", " ", without_marks).strip()


def _compile_pattern(value: str) -> re.Pattern[str] | None:
    normalized = _normalize_pattern(value)
    if not normalized:
        return None
    parts: list[str] = []
    for token in normalized.split():
        wildcard = token.endswith("*")
        literal = token.rstrip("*")
        if not literal:
            continue
        part = re.escape(literal)
        if wildcard:
            part += r"[\w]*"
        parts.append(part)
    if not parts:
        return None
    expression = r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)"
    return re.compile(expression, flags=re.IGNORECASE)


class KeywordMatcher:
    def __init__(self, rules: list[KeywordRule]):
        self.rules = [rule for rule in rules if rule.enabled]
        self._positive: dict[str, list[tuple[str, re.Pattern[str]]]] = {}
        self._negative: dict[str, list[re.Pattern[str]]] = {}
        for rule in self.rules:
            positives: list[tuple[str, re.Pattern[str]]] = []
            for value in (rule.keyword_lv, rule.keyword_en, *rule.variants):
                pattern = _compile_pattern(value)
                if pattern is not None:
                    positives.append((value, pattern))
            self._positive[rule.rule_id] = positives
            self._negative[rule.rule_id] = [
                pattern
                for value in rule.negative_terms
                if (pattern := _compile_pattern(value)) is not None
            ]

    def match(self, tender: Tender) -> MatchResult:
        searchable = canonical_text(tender.text_for_matching)
        tender_cpv = {code.replace("-", "")[:8] for code in tender.cpv_codes if code}
        matched_keywords: list[str] = []
        matched_cpv: set[str] = set()
        score = 0

        for rule in self.rules:
            if any(pattern.search(searchable) for pattern in self._negative[rule.rule_id]):
                continue

            term_match = next(
                (
                    label
                    for label, pattern in self._positive[rule.rule_id]
                    if pattern.search(searchable)
                ),
                None,
            )
            rule_cpv_matches = {
                actual
                for actual in tender_cpv
                if any(
                    actual.startswith(expected.replace("-", "")[:8]) for expected in rule.cpv_codes
                )
            }
            if term_match is None and not rule_cpv_matches:
                continue

            score += rule.weight
            if term_match is not None:
                matched_keywords.append(term_match)
            elif rule.keyword_lv:
                matched_keywords.append(f"{rule.keyword_lv} (CPV)")
            matched_cpv.update(rule_cpv_matches)

        return MatchResult(
            matched_keywords=tuple(dict.fromkeys(matched_keywords)),
            matched_cpv_codes=tuple(sorted(matched_cpv)),
            score=min(100, score),
        )
