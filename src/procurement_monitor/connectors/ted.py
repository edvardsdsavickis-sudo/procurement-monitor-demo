from __future__ import annotations

import logging
import math
from datetime import date
from typing import Any

from procurement_monitor.connectors.base import ProcurementConnector
from procurement_monitor.http import JsonHttpClient
from procurement_monitor.models import Tender, parse_date

LOGGER = logging.getLogger(__name__)


TED_FIELDS = [
    "publication-number",
    "publication-date",
    "notice-type",
    "form-type",
    "title-proc",
    "title-lot",
    "description-proc",
    "description-lot",
    "organisation-name-buyer",
    "organisation-country-buyer",
    "buyer-legal-type",
    "classification-cpv",
    "place-of-performance",
    "deadline-receipt-tender-date-lot",
    "deadline-receipt-tender-time-lot",
    "estimated-value-proc",
    "estimated-value-cur-proc",
    "estimated-value-glo",
    "estimated-value-cur-glo",
    "estimated-value-lot",
    "estimated-value-cur-lot",
    "estimated-value-part",
    "estimated-value-cur-part",
    "framework-maximum-value-glo",
    "framework-maximum-value-cur-glo",
    "framework-maximum-value-lot",
    "framework-maximum-value-cur-lot",
    "framework-value-notice",
    "framework-value-cur-notice",
    "result-value-notice",
    "result-value-cur-notice",
    "result-value-lot",
    "result-value-cur-lot",
    "tender-value",
    "tender-value-cur",
    "submission-url-lot",
]


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _first_string(value: Any) -> str:
    for item in _list(value):
        if isinstance(item, str) and item.strip():
            return item.strip()
    return ""


def _i18n_text(value: Any) -> tuple[str, str]:
    if isinstance(value, str):
        return value.strip(), ""
    if not isinstance(value, dict):
        return "", ""

    preferred = ("eng", "lav", "lit", "est")
    ordered_keys = [*preferred, *(key for key in value if key not in preferred)]
    for language in ordered_keys:
        if language not in value:
            continue
        texts = [
            " ".join(item.split())
            for item in _list(value[language])
            if isinstance(item, str) and item.strip()
        ]
        if texts:
            return "\n".join(dict.fromkeys(texts)), language
    return "", ""


def _numeric_values(value: Any) -> list[float]:
    result: list[float] = []
    for item in _list(value):
        try:
            result.append(float(item))
        except (TypeError, ValueError):
            continue
    return result


def _estimated_value(item: dict[str, Any]) -> tuple[float | None, str]:
    value_fields = (
        ("estimated-value-proc", "estimated-value-cur-proc", "max"),
        ("estimated-value-glo", "estimated-value-cur-glo", "sum"),
        ("estimated-value-lot", "estimated-value-cur-lot", "sum"),
        ("estimated-value-part", "estimated-value-cur-part", "sum"),
        ("framework-maximum-value-glo", "framework-maximum-value-cur-glo", "sum"),
        ("framework-maximum-value-lot", "framework-maximum-value-cur-lot", "sum"),
        ("framework-value-notice", "framework-value-cur-notice", "max"),
        ("result-value-notice", "result-value-cur-notice", "max"),
        ("result-value-lot", "result-value-cur-lot", "sum"),
        ("tender-value", "tender-value-cur", "sum"),
    )
    for value_field, currency_field, aggregation in value_fields:
        values = _numeric_values(item.get(value_field))
        if values:
            amount = max(values) if aggregation == "max" else sum(values)
            return amount, _first_string(item.get(currency_field))
    return None, ""


def _notice_category(notice_type: str, form_type: str) -> str:
    if form_type in {"planning", "consultation"}:
        return "planning"
    if form_type == "competition":
        return "competition"
    if form_type in {"cont-modif", "result", "completion"}:
        return "result"
    if notice_type in {"pin-buyer", "pin-only", "pin-rtl", "pin-tran", "pmc"}:
        return "planning"
    if notice_type.startswith("cn-") or notice_type.startswith("pin-cfc-"):
        return "competition"
    if notice_type in {"qu-sy", "subco"}:
        return "competition"
    if notice_type.startswith("can-") or notice_type in {"compl", "veat"}:
        return "result"
    return "other"


def _html_link(links: Any, publication_number: str) -> str:
    if isinstance(links, dict) and isinstance(links.get("html"), dict):
        html = links["html"]
        for language in ("ENG", "LAV", "LIT", "EST"):
            value = html.get(language)
            if isinstance(value, str) and value:
                return value
        for value in html.values():
            if isinstance(value, str) and value:
                return value
    return f"https://ted.europa.eu/en/notice/-/detail/{publication_number}"


class TedConnector(ProcurementConnector):
    name = "TED"
    endpoint = "https://api.ted.europa.eu/v3/notices/search"

    def __init__(self, client: JsonHttpClient | None = None, page_size: int = 200):
        self.client = client or JsonHttpClient(timeout=60)
        self.page_size = min(max(page_size, 1), 250)

    def fetch(self, start_date: date, end_date: date) -> list[Tender]:
        if end_date < start_date:
            return []

        query = (
            "(place-of-performance IN (LVA LTU EST) "
            "OR buyer-legal-type = eu-ins-bod-ag) "
            f"AND publication-date >= {start_date:%Y%m%d} "
            f"AND publication-date <= {end_date:%Y%m%d}"
        )
        page = 1
        total_pages = 1
        results: list[Tender] = []

        while page <= total_pages:
            payload = {
                "query": query,
                "fields": TED_FIELDS,
                "page": page,
                "limit": self.page_size,
                "scope": "ALL",
                "onlyLatestVersions": True,
                "paginationMode": "PAGE_NUMBER",
            }
            response = self.client.post_json(self.endpoint, payload)
            if not isinstance(response, dict):
                raise RuntimeError("The TED response is not a JSON object")

            notices = response.get("notices", [])
            if not isinstance(notices, list):
                raise RuntimeError("The TED response has no notices list")

            for item in notices:
                if isinstance(item, dict):
                    parsed = self.parse_item(item)
                    if parsed is not None:
                        results.append(parsed)

            total = int(response.get("totalNoticeCount") or 0)
            total_pages = max(1, math.ceil(total / self.page_size))
            if not notices:
                break
            page += 1

        LOGGER.info("TED: received %s notices", len(results))
        return results

    @staticmethod
    def parse_item(item: dict[str, Any]) -> Tender | None:
        publication_number = _first_string(item.get("publication-number"))
        if not publication_number:
            return None

        title, title_language = _i18n_text(item.get("title-proc"))
        if not title:
            title, title_language = _i18n_text(item.get("title-lot"))

        description, description_language = _i18n_text(item.get("description-proc"))
        lot_description, lot_language = _i18n_text(item.get("description-lot"))
        if lot_description and lot_description not in description:
            description = "\n".join(value for value in (description, lot_description) if value)

        issuer, _ = _i18n_text(item.get("organisation-name-buyer"))
        buyer_countries = [
            value
            for value in _list(item.get("organisation-country-buyer"))
            if isinstance(value, str)
        ]
        buyer_types = {
            value for value in _list(item.get("buyer-legal-type")) if isinstance(value, str)
        }
        country = buyer_countries[0] if buyer_countries else ""
        sector = "EU institution" if "eu-ins-bod-ag" in buyer_types else "public sector"

        notice_type = _first_string(item.get("notice-type"))
        form_type = _first_string(item.get("form-type"))
        category = _notice_category(notice_type, form_type)

        publication = parse_date(_first_string(item.get("publication-date")))
        deadline_values = [
            value
            for value in _list(item.get("deadline-receipt-tender-date-lot"))
            if isinstance(value, str)
        ]
        deadlines = sorted(
            parsed for value in deadline_values if (parsed := parse_date(value)) is not None
        )

        estimated_value, currency = _estimated_value(item)

        cpv_codes = sorted(
            {
                str(value).split("-", 1)[0]
                for value in _list(item.get("classification-cpv"))
                if value
            }
        )
        submission_url = _first_string(item.get("submission-url-lot"))
        source_url = _html_link(item.get("links"), publication_number)

        return Tender(
            source="TED",
            source_id=publication_number,
            title=title,
            description=description,
            issuer=issuer,
            issuer_country=country,
            sector=sector,
            notice_type=notice_type or form_type,
            notice_category=category,
            published_date=publication.isoformat() if publication else "",
            deadline=deadlines[0].isoformat() if deadlines else "",
            estimated_value=estimated_value,
            currency=currency,
            cpv_codes=cpv_codes,
            source_url=source_url,
            submission_url=submission_url,
            raw_language=title_language or description_language or lot_language,
        )
