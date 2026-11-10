"""Run the portfolio demo on fictional TED notices."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from procurement_monitor.connectors.ted import TedConnector
from procurement_monitor.matching import KeywordMatcher, load_keyword_csv


def main() -> None:
    matcher = KeywordMatcher(load_keyword_csv(ROOT / "config" / "default_keywords.csv"))
    with (ROOT / "examples" / "sample-notices.json").open(encoding="utf-8") as source:
        notices = json.load(source)["notices"]

    print("# Sample Daily Procurement Digest")
    print("\nDemo schedule: 08:30 local time")
    matched_count = 0
    for notice in notices:
        tender = TedConnector.parse_item(notice)
        if tender is None or not tender.is_opportunity:
            continue
        result = matcher.match(tender)
        if not result.is_match:
            continue
        matched_count += 1
        print(f"\n## {tender.title}")
        print(f"\n- Relevance score: {result.score}/100")
        if result.matched_keywords:
            print(f"- Matched keywords: {', '.join(result.matched_keywords)}")
        if result.matched_cpv_codes:
            print(f"- Matched procurement codes: {', '.join(result.matched_cpv_codes)}")
    print(f"\nMatched {matched_count} of {len(notices)} sample notices.")


if __name__ == "__main__":
    main()
