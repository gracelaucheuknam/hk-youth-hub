"""Eventbrite 香港

Eventbrite 已經停用公開活動搜尋 API（剩返嘅 API 只可以攞你自己主辦嘅活動），
所以要由搜尋頁攞資料。好彩佢個搜尋頁會將成個 result set 以 JSON 形式
塞咗喺 HTML 入面（window.__SERVER_DATA__），所以：

  - 唔使 headless browser
  - 唔使逐個活動入詳情頁（一個 request = 約 20 個活動）
  - 欄位齊過爬 HTML：名稱、日期時間、場地、地址、是否免費、票價、主辦、圖片、標籤

搵唔到 __SERVER_DATA__ 就自動 fallback 去 JSON-LD（<script type="application/ld+json">）。
robots.txt 唔畀抓嘅話，polite_get() 會自動跳過並喺 log 講返。
"""
from __future__ import annotations

import re
import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup

from .base import Item, polite_get, clean, parse_age

log = logging.getLogger(__name__)

SOURCE = "eventbrite"
SOURCE_LABEL = "Eventbrite 香港"
SOURCE_TYPE = "活動平台"
BASE = "https://www.eventbrite.hk"

# 想抓咩就喺呢度加，key 淨係方便睇 log
SEARCHES = {
    "免費活動": "/d/hong-kong-sar/free--events/",
    "工作坊": "/d/hong-kong-sar/free--workshops/",
    "講座": "/d/hong-kong-sar/free--seminars/",
}
MAX_PAGES = 5                    # 每個搜尋最多幾多頁（一頁約 20 個）

SERVER_DATA = re.compile(r"window\.__SERVER_DATA__\s*=\s*(\{.*?\});?\s*</script>", re.S)

# Eventbrite 嘅英文分類 → 我哋嘅中文類別
CAT_MAP = {
    "Class, Training, or Workshop": "工作坊", "Workshop": "工作坊",
    "Seminar or Talk": "講座", "Conference": "講座", "Networking": "交流",
    "Science & Technology": "創業", "Business & Professional": "就業",
    "Career": "就業", "Education": "進修",
    "Music": "文娛消閒", "Performing & Visual Arts": "文娛消閒",
    "Film, Media & Entertainment": "文娛消閒", "Arts": "文娛消閒",
    "Community & Culture": "社區參與", "Charity & Causes": "社區參與",
    "Health & Wellness": "文娛消閒", "Sports & Fitness": "文娛消閒",
}


def _server_data(html: str) -> dict | None:
    m = SERVER_DATA.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        log.warning("__SERVER_DATA__ 解析失敗")
        return None


def _results(data: dict) -> list[dict]:
    for path in (("search_data", "events", "results"),
                 ("search_data", "events", "hits"),
                 ("events", "results")):
        node = data
        for k in path:
            node = node.get(k) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, list):
            return node
    return []


def _jsonld_events(html: str) -> list[dict]:
    """後備方案：原站改咗 __SERVER_DATA__ 都仲有結構化資料。"""
    out = []
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            blob = json.loads(tag.string or "{}")
        except json.JSONDecodeError:
            continue
        items = blob if isinstance(blob, list) else [blob]
        for it in items:
            if isinstance(it, dict) and it.get("@type") == "Event":
                out.append(it)
    return out


def _from_server_data(e: dict) -> Item | None:
    eid = str(e.get("id") or e.get("eid") or "")
    name = clean(e.get("name") or "")
    url = e.get("url") or ""
    if not (eid and name and url):
        return None

    venue = e.get("primary_venue") or {}
    addr = (venue.get("address") or {})
    online = bool(e.get("is_online_event"))
    place = clean(venue.get("name") or "")
    full_addr = clean(addr.get("localized_address_display") or "")

    tickets = e.get("ticket_availability") or {}
    is_free = tickets.get("is_free")
    price = (tickets.get("minimum_ticket_price") or {}).get("display") or ""
    if is_free is True:
        fee_text = "免費"
    elif price:
        fee_text = f"由 {price} 起"
        is_free = False
    else:
        fee_text, is_free = "未列明", None

    tags = [clean(t.get("display_name", "")) for t in (e.get("tags") or [])
            if t.get("display_name")]
    cats = sorted({CAT_MAP[t] for t in tags if t in CAT_MAP}) or ["活動"]

    start = (e.get("start_date") or "") or None
    end = (e.get("end_date") or "") or start
    st, et = e.get("start_time") or "", e.get("end_time") or ""
    time_text = f"{st} - {et}".strip(" -")

    date_text = ""
    if start:
        try:
            date_text = datetime.fromisoformat(start).strftime("%d-%m-%Y")
            if end and end != start:
                date_text += " ～ " + datetime.fromisoformat(end).strftime("%d-%m-%Y")
        except ValueError:
            date_text = start

    summary = clean(e.get("summary") or "")[:280]
    img = ((e.get("image") or {}).get("original") or {}).get("url") \
        or (e.get("image") or {}).get("url") or ""
    organiser = clean((e.get("primary_organizer") or {}).get("name") or "")
    age_min, age_max = parse_age(f"{name} {summary}")

    return Item(
        id=f"{SOURCE}:{eid}",
        source=SOURCE,
        source_label=SOURCE_LABEL,
        source_type=SOURCE_TYPE,
        title=name,
        url=url,
        kind="活動",
        categories=cats,
        tags=[t for t in tags if t not in CAT_MAP][:4],
        organiser=organiser,
        venue="網上活動" if online else clean(f"{place} {full_addr}"),
        region="網上" if online else "香港",
        start_date=start,
        end_date=end,
        date_text=date_text,
        time_text=time_text,
        audience="",
        age_min=age_min,
        age_max=age_max,
        is_free=is_free,
        fee_text=fee_text,
        apply_url=url,                # Eventbrite 本身就係報名頁
        summary=summary,
        image=img,
    )


def _from_jsonld(e: dict) -> Item | None:
    url = e.get("url") or ""
    name = clean(e.get("name") or "")
    if not (url and name):
        return None
    eid = url.rstrip("/").rsplit("-", 1)[-1]
    loc = e.get("location") or {}
    offers = e.get("offers")
    offers = offers[0] if isinstance(offers, list) and offers else (offers or {})
    price = str(offers.get("price") or "")
    is_free = True if price in ("0", "0.0", "0.00") else (False if price else None)
    start = (e.get("startDate") or "")[:10] or None
    end = (e.get("endDate") or "")[:10] or start
    return Item(
        id=f"{SOURCE}:{eid}", source=SOURCE, source_label=SOURCE_LABEL,
        source_type=SOURCE_TYPE, title=name, url=url, kind="活動",
        categories=["活動"], organiser=clean((e.get("organizer") or {}).get("name") or ""),
        venue=clean(loc.get("name") or ""), region="香港",
        start_date=start, end_date=end,
        is_free=is_free, fee_text="免費" if is_free else "未列明",
        apply_url=url, summary=clean(e.get("description") or "")[:280],
        image=(e.get("image") if isinstance(e.get("image"), str) else "") or "",
    )


def scrape() -> list[dict]:
    items: dict[str, dict] = {}
    for label, path in SEARCHES.items():
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE}{path}" + (f"?page={page}" if page > 1 else "")
            html = polite_get(url)
            if not html:
                break

            data = _server_data(html)
            raw = _results(data) if data else []
            parser = _from_server_data

            if not raw:                                  # 後備
                raw = _jsonld_events(html)
                parser = _from_jsonld
                if raw:
                    log.warning("[%s] __SERVER_DATA__ 攞唔到，改用 JSON-LD", SOURCE)

            if not raw:
                log.error("[%s] %s 第 %d 頁攞唔到任何活動（原站可能改版）",
                          SOURCE, label, page)
                break

            before = len(items)
            for e in raw:
                try:
                    it = parser(e)
                    if it:
                        items[it.id] = it.finalize()
                except Exception as ex:  # noqa: BLE001
                    log.exception("parse 失敗：%s", ex)
            log.info("[%s] %s 第 %d 頁 → 新增 %d 個", SOURCE, label, page,
                     len(items) - before)
            if len(items) == before:                     # 冇新嘢 = 到底
                break

    log.info("[%s] 成功抓到 %d 個活動", SOURCE, len(items))
    return list(items.values())
