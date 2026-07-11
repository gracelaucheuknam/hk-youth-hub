"""新來源範本：copy 一份改名，寫 discover_urls() + parse_detail()，
再喺 scrapers/__init__.py 加返入 SCRAPERS 就得。

建議次序（由易到難）：
  1. artmate      — art-mate.net，列表 + 詳情都係直出 HTML
  2. eventbrite   — 有官方 API（免費 key），比爬 HTML 穩陣
  3. socialcareer — 義工活動，睇下有冇 JSON endpoint（Network tab）
  4. erb / labour — 課程同計劃，屬「計劃」而非「活動」，kind='課程'
"""
from __future__ import annotations
import logging
from .base import Item, polite_get, clean, guess_fee, guess_region, parse_age

log = logging.getLogger(__name__)

SOURCE = "example"
SOURCE_LABEL = "示例機構"
SOURCE_TYPE = "非牟利"


def discover_urls() -> list[str]:
    return []


def parse_detail(url: str) -> Item | None:
    return None


def scrape() -> list[dict]:
    items = []
    for url in discover_urls():
        try:
            it = parse_detail(url)
            if it:
                items.append(it.finalize())
        except Exception as e:  # noqa: BLE001
            log.exception("parse 失敗 %s: %s", url, e)
    return items
