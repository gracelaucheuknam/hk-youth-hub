"""政府青少年網站 Youth.gov.hk

結構（2026-07 實測）：
  列表頁：/tc/{section}/activities            伺服器直出 HTML，唔使 JS
  詳情頁：/tc/{section}/activities/{uuid}     欄位齊全（日期/時間/地點/主辦/報名方式…）

抓法：4 個分頁列表 → 抽晒 uuid 連結 → 逐個入詳情頁 parse。
"""
from __future__ import annotations

import re
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import (
    Item, polite_get, clean, parse_date, parse_date_range,
    parse_age, guess_fee, guess_region,
)

log = logging.getLogger(__name__)

SOURCE = "youth_gov"
SOURCE_LABEL = "政府青少年網站"
SOURCE_TYPE = "政府"
BASE = "https://www.youth.gov.hk"

SECTIONS = {
    "career-study": "升學就業",
    "startup": "創業",
    "community-participation": "社區參與",
    "cultural-leisure": "文娛消閒",
}

DETAIL_RE = re.compile(
    r"/tc/(career-study|startup|community-participation|cultural-leisure)/activities/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)

# 詳情頁嘅欄位標籤（網站自己嘅用字）
LABELS = ["日期", "時間", "地點", "主辦機構", "備註", "報名方式", "查詢電郵",
          "截止日期", "報名截止日期", "費用", "對象", "活動對象", "名額"]


def discover_urls() -> list[str]:
    """由列表頁抽所有活動詳情連結（去重）。"""
    seen: dict[str, None] = {}
    pages = [f"{BASE}/tc/activities"] + [
        f"{BASE}/tc/{s}/activities" for s in SECTIONS
    ]
    for page in pages:
        html = polite_get(page)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]"):
            m = DETAIL_RE.search(a["href"])
            if m:
                seen.setdefault(urljoin(BASE, m.group(0)), None)
    log.info("[%s] 搵到 %d 個活動連結", SOURCE, len(seen))
    return list(seen)


def _field(soup: BeautifulSoup, label: str) -> str:
    """
    詳情頁係『標籤 / 內容』上下排。搵到文字剛好等於標籤嘅元素，
    再攞佢之後最近嘅有內容元素。網站改 class 都唔會爆。
    """
    for el in soup.find_all(string=True):
        if clean(str(el)) == label:
            node = el.parent
            for sib in node.find_all_next():
                txt = clean(sib.get_text(" ", strip=True))
                if not txt or txt in LABELS:
                    continue
                if txt == label:
                    continue
                return txt
    return ""


def parse_detail(url: str) -> Item | None:
    html = polite_get(url, allow_404=True)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    main = soup.find("main") or soup.find(id="main-content") or soup
    h1 = main.find("h1")
    title = clean(h1.get_text()) if h1 else ""
    if not title:
        log.warning("冇標題，跳過：%s", url)
        return None

    m = DETAIL_RE.search(url)
    section = SECTIONS.get(m.group(1), "") if m else ""
    uid = m.group(2) if m else url.rsplit("/", 1)[-1]

    # 分類：詳情頁會列晒佢屬於邊幾個板塊
    cats = {section} if section else set()
    for a in main.select('a[href*="/tc/"]'):
        label = clean(a.get_text())
        if label in SECTIONS.values():
            cats.add(label)

    tags = sorted({
        clean(a.get_text()).lstrip("#")
        for a in main.select('a[href*="/tc/tags/"]')
        if clean(a.get_text())
    })

    date_text = _field(soup, "日期")
    start, end = parse_date_range(date_text)
    venue = _field(soup, "地點")
    organiser = _field(soup, "主辦機構")
    remarks = _field(soup, "備註")
    apply_way = _field(soup, "報名方式")
    enquiry = _field(soup, "查詢電郵")
    deadline_txt = _field(soup, "截止日期") or _field(soup, "報名截止日期")

    # 對象：優先用欄位，冇就攞正文「活動對象」之後嗰段
    audience = _field(soup, "活動對象") or _field(soup, "對象")
    if not audience:
        for h in main.find_all(re.compile("^h[3-6]$")):
            if "對象" in clean(h.get_text()):
                nxt = h.find_next(["ul", "p"])
                if nxt:
                    audience = clean(nxt.get_text(" ", strip=True))
                break

    body = clean(main.get_text(" ", strip=True))[:4000]
    summary = ""
    for h in main.find_all(re.compile("^h[3-6]$")):
        if "活動內容" in clean(h.get_text()) or "內容" == clean(h.get_text()):
            p = h.find_next("p")
            if p:
                summary = clean(p.get_text())[:280]
            break

    is_free, fee_text = guess_fee(_field(soup, "費用"), remarks, body)
    age_min, age_max = parse_age(audience or body)

    apply_url = ""
    for a in main.select("a[href^=http]"):
        txt = clean(a.get_text())
        if any(k in txt for k in ["線上申請", "網上報名", "報名", "立即申請", "登記"]) \
                and "youth.gov.hk" not in a["href"]:
            apply_url = a["href"]
            break

    img = ""
    for i in main.select("img[src]"):
        if "/storage/assets/collections/" in i["src"] and "facebook" not in i["src"]:
            img = urljoin(BASE, i["src"])
            break

    updated = None
    m2 = re.search(r"最後更新日期[:：]?\s*(\d{4}年\d{1,2}月\d{1,2}日)", body)
    if m2:
        updated = parse_date(m2.group(1))

    return Item(
        id=f"{SOURCE}:{uid}",
        source=SOURCE,
        source_label=SOURCE_LABEL,
        source_type=SOURCE_TYPE,
        title=title,
        url=url,
        kind="活動",
        categories=sorted(cats),
        tags=tags,
        organiser=organiser,
        venue=venue,
        region=guess_region(venue, title, body[:500]),
        start_date=start,
        end_date=end,
        date_text=date_text,
        time_text=_field(soup, "時間"),
        deadline=parse_date(deadline_txt) if deadline_txt else None,
        audience=audience,
        age_min=age_min,
        age_max=age_max,
        is_free=is_free,
        fee_text=fee_text,
        apply_url=apply_url,
        enquiry=enquiry,
        summary=summary or (apply_way[:200] if apply_way else ""),
        image=img,
        updated=updated,
    )


def scrape() -> list[dict]:
    items: list[dict] = []
    for url in discover_urls():
        try:
            item = parse_detail(url)
            if item:
                items.append(item.finalize())
        except Exception as e:  # noqa: BLE001  一個活動爆咗，唔好拖冧成個 run
            log.exception("parse 失敗 %s：%s", url, e)
    log.info("[%s] 成功抓到 %d 個活動", SOURCE, len(items))
    return items
