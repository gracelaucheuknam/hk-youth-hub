#!/usr/bin/env python3
"""跑晒所有 scraper，合併、去重、寫入 docs/data/。

用法：
    python build.py                # 全部來源
    python build.py --only youth_gov
    python build.py --keep-days 60 # 已完結活動保留幾耐（預設 30 日）
"""
from __future__ import annotations

import json
import shutil
import logging
import argparse
from pathlib import Path
from datetime import date, datetime, timedelta

from scrapers import SCRAPERS

ROOT = Path(__file__).parent
OUT = ROOT / "docs" / "data"
EVENTS = OUT / "events.json"
META = OUT / "meta.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build")


def load_existing() -> list[dict]:
    if EVENTS.exists():
        return json.loads(EVENTS.read_text("utf-8"))
    return []


def merge(old: list[dict], new: list[dict], sources_run: set[str], keep_days: int) -> list[dict]:
    """
    新資料蓋舊資料（同 id）。
    今次冇跑嘅來源，舊資料照留。
    今次跑咗但原站已經冇咗嘅項目 → 當落咗架，如果仲未過期就保留並標記。
    """
    cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
    merged: dict[str, dict] = {it["id"]: it for it in old}
    new_ids = {it["id"] for it in new}

    for it in new:
        prev = merged.get(it["id"], {})
        it["first_seen"] = prev.get("first_seen") or it["scraped_at"]
        it["delisted"] = False
        merged[it["id"]] = it

    for _id, it in list(merged.items()):
        if it["source"] in sources_run and _id not in new_ids:
            it["delisted"] = True
        # 完結太耐就清走，唔好無限膨脹
        end = it.get("end_date") or it.get("start_date")
        if end and end < cutoff:
            merged.pop(_id)

    def sort_key(it: dict):
        return (it.get("start_date") or "9999-12-31", it["title"])

    return sorted(merged.values(), key=sort_key)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=list(SCRAPERS), default=list(SCRAPERS))
    ap.add_argument("--keep-days", type=int, default=30)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    old = load_existing()

    collected: list[dict] = []
    stats: dict[str, int | str] = {}
    ok_sources: set[str] = set()

    for name in args.only:
        log.info("▶ 開始抓 %s", name)
        try:
            items = SCRAPERS[name]()
            if items:                       # 抓到 0 個多數係網站改版 → 保留舊資料
                collected += items
                ok_sources.add(name)
                stats[name] = len(items)
            else:
                stats[name] = "0（保留舊資料，請檢查 selector）"
                log.error("⚠ %s 抓到 0 個項目，可能原站改版", name)
        except Exception as e:  # noqa: BLE001
            stats[name] = f"失敗：{e}"
            log.exception("✖ %s 整個 scraper 失敗", name)

    merged = merge(old, collected, ok_sources, args.keep_days)

    if EVENTS.exists():                     # 出事可以 rollback
        shutil.copy(EVENTS, OUT / "events.prev.json")

    EVENTS.write_text(json.dumps(merged, ensure_ascii=False, indent=1), "utf-8")

    today = date.today().isoformat()
    upcoming = sum(1 for i in merged if (i.get("end_date") or "9999") >= today
                   and not i.get("delisted"))
    META.write_text(json.dumps({
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "total": len(merged),
        "upcoming": upcoming,
        "sources": stats,
        "source_labels": sorted({i["source_label"] for i in merged}),
    }, ensure_ascii=False, indent=1), "utf-8")

    log.info("✓ 完成：共 %d 個項目（%d 個未完結）→ %s", len(merged), upcoming, EVENTS)


if __name__ == "__main__":
    main()
