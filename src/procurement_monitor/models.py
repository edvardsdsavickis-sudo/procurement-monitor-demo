from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def canonical_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    cleaned = value.strip()
    candidates = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%Y-%m-%d%z",
        "%Y-%m-%dT%H:%M:%S%z",
    )
    for fmt in candidates:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00")).date()
    except ValueError:
        return None


@dataclass(slots=True)
class Tender:
    source: str
    source_id: str
    title: str
    description: str
    issuer: str
    issuer_country: str
    sector: str
    notice_type: str
    notice_category: str
    published_date: str
    deadline: str
    estimated_value: float | None
    currency: str
    cpv_codes: list[str]
    source_url: str
    submission_url: str
    raw_language: str = ""
    award_criteria: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    matched_cpv_codes: list[str] = field(default_factory=list)
    deterministic_score: int = 0
    first_seen_at: str = field(default_factory=utc_now_iso)
    immediate_sent_at: str = ""
    digest_sent_at: str = ""

    @property
    def source_key(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def fingerprint(self) -> str:
        title = canonical_text(self.title)
        issuer = canonical_text(self.issuer)
        date_part = self.deadline or self.published_date
        digest = hashlib.sha256(f"{issuer}|{title}|{date_part}".encode()).hexdigest()
        return digest[:32]

    @property
    def is_opportunity(self) -> bool:
        return self.notice_category in {"planning", "competition", "amendment", "other"}

    @property
    def preparation_days(self) -> int | None:
        if self.notice_category != "competition":
            return None
        publication = parse_date(self.published_date)
        submission = parse_date(self.deadline)
        if publication is None or submission is None:
            return None
        return max(0, (submission - publication).days)

    @property
    def text_for_matching(self) -> str:
        parts = [self.title, self.description, *self.cpv_codes]
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class KeywordRule:
    rule_id: str
    category: str
    keyword_lv: str
    keyword_en: str
    variants: tuple[str, ...]
    cpv_codes: tuple[str, ...]
    negative_terms: tuple[str, ...]
    weight: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class MatchResult:
    matched_keywords: tuple[str, ...]
    matched_cpv_codes: tuple[str, ...]
    score: int

    @property
    def is_match(self) -> bool:
        return bool(self.matched_keywords or self.matched_cpv_codes)
