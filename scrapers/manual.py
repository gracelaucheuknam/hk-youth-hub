"""人手維護來源（data/manual.csv）

有啲嘢唔係「活動流」，而係長期計劃（YETP、Y.E.S.、大灣區實習計劃…），
一年改一兩次，寫 scraper 唔抵，而且好多都係 SPA／要登入／robots 唔畀抓。

呢個「scraper」只係讀 data/manual.csv，轉做統一格式，同其他來源一齊顯示。
你用 Excel 開個 CSV、改完存返（記得存 UTF-8），下次 build 就生效。

CSV 欄位（缺咗嘅可以留空）：
  title, url, kind, categories, tags, organiser, venue, region,
  start_date, end_date, deadline, audience, age_min, age_max,
  is_free, fee_text, deposit, apply_url, enquiry, summary, source_label, source_type

  categories / tags：用「｜」分隔多個值，例：就業｜進修
  is_free：TRUE / FALSE / 留空（＝未列明）
  日期：YYYY-MM-DD；長期計劃留空即可（前端會顯示「日期待定」）
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from .base import Item, clean

log = logging.getLogger(__name__)

SOURCE = "manual"
CSV_PATH = Path(__file__).parent.parent / "data" / "manual.csv"


def _bool(v: str) -> bool | None:
    v = clean(v).upper()
    if v in ("TRUE", "T", "YES", "Y", "1", "是"):
        return True
    if v in ("FALSE", "F", "NO", "N", "0", "否"):
        return False
    return None


def _int(v: str) -> int | None:
    v = clean(v)
    return int(v) if v.isdigit() else None


def _list(v: str) -> list[str]:
    return [x for x in (clean(p) for p in clean(v).split("｜")) if x]


def scrape() -> list[dict]:
    if not CSV_PATH.exists():
        log.warning("[%s] 搵唔到 %s，跳過", SOURCE, CSV_PATH)
        return []

    items = []
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            title = clean(row.get("title", ""))
            url = clean(row.get("url", ""))
            if not title or not url:
                log.warning("[%s] 第 %d 行冇 title 或 url，跳過", SOURCE, i)
                continue
            try:
                it = Item(
                    id=f"{SOURCE}:{title}",
                    source=SOURCE,
                    source_label=clean(row.get("source_label", "")) or "人手整理",
                    source_type=clean(row.get("source_type", "")) or "政府",
                    title=title,
                    url=url,
                    kind=clean(row.get("kind", "")) or "計劃",
                    categories=_list(row.get("categories", "")) or ["就業"],
                    tags=_list(row.get("tags", "")),
                    organiser=clean(row.get("organiser", "")),
                    venue=clean(row.get("venue", "")),
                    region=clean(row.get("region", "")) or "香港",
                    start_date=clean(row.get("start_date", "")) or None,
                    end_date=clean(row.get("end_date", "")) or None,
                    date_text=clean(row.get("date_text", "")) or "全年接受申請",
                    deadline=clean(row.get("deadline", "")) or None,
                    audience=clean(row.get("audience", "")),
                    age_min=_int(row.get("age_min", "")),
                    age_max=_int(row.get("age_max", "")),
                    is_free=_bool(row.get("is_free", "")),
                    fee_text=clean(row.get("fee_text", "")) or "未列明",
                    deposit=clean(row.get("deposit", "")),
                    apply_url=clean(row.get("apply_url", "")),
                    enquiry=clean(row.get("enquiry", "")),
                    summary=clean(row.get("summary", ""))[:280],
                )
                items.append(it.finalize())
            except Exception as e:  # noqa: BLE001
                log.exception("[%s] 第 %d 行出錯：%s", SOURCE, i, e)

    log.info("[%s] 讀咗 %d 個人手項目", SOURCE, len(items))
    return items
