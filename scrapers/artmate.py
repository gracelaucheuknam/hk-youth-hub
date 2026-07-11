"""art-mate.net（藝文活動平台）

結構（2026-07 實測）：
  列表頁：/group/hk_coming_performance?tag={標籤}&page={n}   直出 HTML，有分頁
  詳情頁：/doc/{id}

詳情頁嘅資訊區用 icon 做前綴（L=地點、S=日期時間、M=票價／按金），
所以唔靠 CSS class，靠內容規律嚟分辨，原站改版都唔易爆。
"""
from __future__ import annotations

import re
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Item, polite_get, clean, parse_age, guess_region

log = logging.getLogger(__name__)

SOURCE = "artmate"
SOURCE_LABEL = "art-mate 藝文平台"
SOURCE_TYPE = "活動平台"
BASE = "https://www.art-mate.net"
LIST = f"{BASE}/group/hk_coming_performance"

# 只抓對青年有用嘅類型（唔係抓晒成個站，減少對方負擔）
CRAWL_TAGS = ["免費", "工作坊", "講座", "課程", "導賞"]
MAX_PAGES = 3                       # 每個標籤最多抓幾多頁（一頁約 20 個）

# 原站嘅標籤詞彙（用嚟由連住一齊嘅標籤字串拆返做 list）
TAG_VOCAB = [
    "南豐紗廠 / CHAT六廠", "套票優惠", "早鳥優惠", "手作DIY", "視覺藝術", "Art Tech",
    "青年廣場", "大劇場", "演唱會", "棟篤笑", "合家歡", "藝穗會", "身心靈",
    "免費", "劇場", "音樂", "舞蹈", "戲曲", "多媒體", "電影", "文學", "攝影",
    "設計", "文化", "工作坊", "講座", "導賞", "課程", "ACG", "演出", "放映",
    "展覽", "在線", "內地", "深圳", "JCCAC", "HKAC", "大館", "PMQ", "東蒲",
    "WestK", "濱海", "CHAT", "暑假", "活動", "其他",
]
TAG_VOCAB.sort(key=len, reverse=True)          # 長嘅行先，避免「文化」食咗「文化節」

# 邊啲標籤當「類別」（可以做篩選），其餘當一般 tag
CATEGORY_TAGS = {"工作坊", "講座", "導賞", "課程", "展覽", "演出", "放映",
                 "演唱會", "劇場", "音樂", "舞蹈", "戲曲", "視覺藝術", "電影"}

DOC_RE = re.compile(r"/doc/(\d+)")
ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
MONEY = re.compile(r"(免費|HKD|HK\$|\$\s?\d|按金|全免)")
DEPOSIT = re.compile(r"按金\s*(HKD?\s*[\d,]+|\$[\d,]+)")
ICON_PREFIX = re.compile(r"^[A-Z](?=[^A-Za-z\s])")     # 「L陳廷驊…」「S2026-07-12」


def discover_urls() -> list[str]:
    seen: dict[str, None] = {}
    for tag in CRAWL_TAGS:
        for page in range(1, MAX_PAGES + 1):
            url = f"{LIST}?tag={tag}" + (f"&page={page}" if page > 1 else "")
            html = polite_get(url)
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")
            before = len(seen)
            for a in soup.select('a[href*="/doc/"]'):
                m = DOC_RE.search(a["href"])
                if m:
                    seen.setdefault(f"{BASE}/doc/{m.group(1)}", None)
            if len(seen) == before:            # 呢頁冇新嘢 → 冇下一頁
                break
    log.info("[%s] 搵到 %d 個節目連結", SOURCE, len(seen))
    return list(seen)


def _split_tags(text: str) -> list[str]:
    """『設計文化講座活動免費南豐紗廠 / CHAT六廠合家歡』→ list"""
    out, rest = [], clean(text)
    changed = True
    while rest and changed:
        changed = False
        for t in TAG_VOCAB:
            if rest.startswith(t):
                out.append(t)
                rest = rest[len(t):].strip()
                changed = True
                break
    return out


def _collect_tags(h1) -> list[str]:
    """標籤條就喺 h1 上面，可能係一嚿字，亦可能拆成幾個 span。"""
    tags: list[str] = []
    for s in h1.find_all_previous(string=True, limit=40):
        t = clean(str(s))
        if not t:
            continue
        got = _split_tags(t)
        if not got:
            break                       # 撞到唔係標籤嘅嘢就收手
        tags = got + tags
    return list(dict.fromkeys(tags))


def _info_lines(h1) -> list[str]:
    """h1 之後、『簡介』之前嘅資訊行（地點／日期／票價／主辦）。"""
    lines = []
    for s in h1.find_all_next(string=True, limit=120):
        t = clean(str(s))
        if t in ("簡介", "製作／參與人員", "購票／報名"):
            break
        if t:
            lines.append(ICON_PREFIX.sub("", t))
    return lines


def parse_detail(url: str) -> Item | None:
    html = polite_get(url, allow_404=True)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if not h1:
        return None
    title = clean(h1.get_text())
    if not title:
        return None

    uid = DOC_RE.search(url).group(1)
    tags = _collect_tags(h1)

    organiser = ""
    org = soup.select_one('a[href*="/group/database?name="]')
    if org:
        organiser = clean(org.get_text())

    dates, price_line, venue = [], "", ""
    for line in _info_lines(h1):
        if line in ("主辦", "合辦", "協辦", organiser):
            continue
        if ISO_DATE.search(line):
            dates.append(line)
        elif MONEY.search(line) and not price_line:
            price_line = line
        elif not venue and len(line) > 1 and not line.startswith("http"):
            venue = line

    iso = sorted({f"{y}-{m}-{d}" for y, m, d in
                  (ISO_DATE.search(x).groups() for x in dates if ISO_DATE.search(x))})
    start = iso[0] if iso else None
    end = iso[-1] if iso else None

    time_text = ""
    if dates:
        tm = re.search(r"\(([^)]+)\)", dates[0])
        if tm:
            time_text = clean(tm.group(1))

    # 費用同按金
    is_free = None
    if "免費" in tags or "免費" in price_line or "全免" in price_line:
        is_free = True
        fee_text = "免費"
    elif MONEY.search(price_line):
        is_free = False
        fee_text = price_line
    else:
        fee_text = "未列明"
    dep = DEPOSIT.search(price_line)
    deposit = clean(dep.group(1)) if dep else ""

    # 簡介
    summary = ""
    for h in soup.find_all(re.compile("^h[1-6]$")):
        if clean(h.get_text()) == "簡介":
            p = h.find_next("p")
            if p:
                summary = clean(p.get_text())[:280]
            break

    apply_url = ""
    for a in soup.select("a[href]"):
        if clean(a.get_text()) in ("立即報名", "立即購票", "報名"):
            apply_url = urljoin(BASE, a["href"])
            break

    enquiry = ""
    mail = soup.select_one('a[href^="mailto:"]')
    if mail:
        enquiry = mail["href"].replace("mailto:", "")

    img = ""
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        img = og["content"]

    cats = [t for t in tags if t in CATEGORY_TAGS] or ["文娛消閒"]
    age_min, age_max = parse_age(f"{summary} {' '.join(tags)}")

    return Item(
        id=f"{SOURCE}:{uid}",
        source=SOURCE,
        source_label=SOURCE_LABEL,
        source_type=SOURCE_TYPE,
        title=title,
        url=url,
        kind="活動",
        categories=cats,
        tags=[t for t in tags if t not in CATEGORY_TAGS],
        organiser=organiser,
        venue=venue,
        region=guess_region(venue, " ".join(tags)),
        start_date=start,
        end_date=end,
        date_text=" / ".join(dates[:2]),
        time_text=time_text,
        audience="",
        age_min=age_min,
        age_max=age_max,
        is_free=is_free,
        fee_text=fee_text,
        deposit=deposit,
        apply_url=apply_url,
        enquiry=enquiry,
        summary=summary,
        image=img,
    )


def scrape() -> list[dict]:
    items = []
    for url in discover_urls():
        try:
            it = parse_detail(url)
            if it:
                items.append(it.finalize())
        except Exception as e:  # noqa: BLE001
            log.exception("parse 失敗 %s：%s", url, e)
    log.info("[%s] 成功抓到 %d 個節目", SOURCE, len(items))
    return items
