"""共用工具：禮貌抓取（robots.txt / 限速 / 重試）、文字與日期處理。

所有 scraper 都應該用 polite_get()，唔好直接 requests.get()。
"""
from __future__ import annotations

import re
import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import requests

log = logging.getLogger(__name__)

# 表明身分 + 留聯絡方法，係最基本嘅網絡禮儀
USER_AGENT = (
    "HKYouthHubBot/1.0 (+https://github.com/gracelaucheuknam/hk-youth-hub; "
    "non-commercial youth opportunity aggregator; "
    "contact: gracelaucheuknam@gmail.com)"
)
REQUEST_DELAY = 1.5      # 每個 request 之間至少隔幾多秒
TIMEOUT = 25
MAX_RETRY = 3

_session = requests.Session()
_session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "zh-HK,zh-TW;q=0.9,en;q=0.8",
})

_robots_cache: dict[str, RobotFileParser] = {}
_last_request_at: dict[str, float] = {}


def _robots_allowed(url: str) -> bool:
    """檢查 robots.txt。取唔到 robots.txt 就當作允許（同大部分 crawler 一致）。"""
    parts = urlparse(url)
    root = f"{parts.scheme}://{parts.netloc}"
    rp = _robots_cache.get(root)
    if rp is None:
        rp = RobotFileParser()
        rp.set_url(urljoin(root, "/robots.txt"))
        try:
            rp.read()
        except Exception as e:  # noqa: BLE001
            log.warning("讀唔到 %s/robots.txt（%s），當作允許", root, e)
            rp.allow_all = True
        _robots_cache[root] = rp
    return rp.can_fetch(USER_AGENT, url)


def polite_get(url: str, *, allow_404: bool = False,
               headers: dict | None = None) -> str | None:
    """守 robots.txt、按 host 限速、失敗重試。回傳 HTML 文字。
    同一個 _session，所以 cookie（例如 ASP.NET session）會自動跟住。"""
    if not _robots_allowed(url):
        log.warning("robots.txt 唔畀抓，跳過：%s", url)
        return None

    host = urlparse(url).netloc
    gap = time.time() - _last_request_at.get(host, 0)
    if gap < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - gap)

    for attempt in range(1, MAX_RETRY + 1):
        try:
            r = _session.get(url, timeout=TIMEOUT, headers=headers or {})
            _last_request_at[host] = time.time()
            if r.status_code == 404 and allow_404:
                return None
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:  # noqa: BLE001
            wait = 2 ** attempt
            log.warning("抓取失敗（第 %d 次）%s：%s，%d 秒後重試", attempt, url, e, wait)
            time.sleep(wait)
            _last_request_at[host] = time.time()
    log.error("放棄：%s", url)
    return None


def polite_post(url: str, payload: dict, headers: dict | None = None) -> dict | None:
    """POST JSON（GraphQL 等）。同樣守 robots.txt 同限速。"""
    if not _robots_allowed(url):
        log.warning("robots.txt 唔畀，跳過：%s", url)
        return None

    host = urlparse(url).netloc
    gap = time.time() - _last_request_at.get(host, 0)
    if gap < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - gap)

    for attempt in range(1, MAX_RETRY + 1):
        try:
            r = _session.post(url, json=payload, headers=headers or {}, timeout=TIMEOUT)
            _last_request_at[host] = time.time()
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            wait = 2 ** attempt
            log.warning("POST 失敗（第 %d 次）%s：%s，%d 秒後重試", attempt, url, e, wait)
            time.sleep(wait)
            _last_request_at[host] = time.time()
    log.error("放棄 POST：%s", url)
    return None


# ---------------------------------------------------------------- 文字 / 日期

WS = re.compile(r"\s+")


def clean(text: str | None) -> str:
    return WS.sub(" ", (text or "")).strip()


DATE_PATTERNS = [
    (re.compile(r"(\d{2})-(\d{2})-(\d{4})"), "%d-%m-%Y"),          # 13-07-2026
    (re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"), "zh"),          # 2026年6月25日
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "%Y-%m-%d"),          # 2026-07-13
]


def parse_date(text: str) -> str | None:
    """由任意文字抽第一個日期，回傳 ISO 字串 YYYY-MM-DD。"""
    text = clean(text)
    for pat, fmt in DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if fmt == "zh":
                y, mo, d = (int(x) for x in m.groups())
                return date(y, mo, d).isoformat()
            return datetime.strptime(m.group(0), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_date_range(text: str) -> tuple[str | None, str | None]:
    """『13-07-2026 ～ 20-09-2026』→ ('2026-07-13', '2026-09-20')。單日就兩個都一樣。"""
    text = clean(text)
    parts = re.split(r"[～~至到\-–—]{1}\s*(?=\d{2}-\d{2}-\d{4}|\d{4})", text)
    dates = [d for d in (parse_date(p) for p in [text]) if d]
    found = []
    for pat, _ in DATE_PATTERNS[:1]:
        found = pat.findall(text)
    if len(found) >= 2:
        return parse_date(f"{found[0][0]}-{found[0][1]}-{found[0][2]}"), \
               parse_date(f"{found[1][0]}-{found[1][1]}-{found[1][2]}")
    single = parse_date(text)
    return single, single


AGE_RANGE = re.compile(r"(\d{1,2})\s*(?:至|-|–|~)\s*(\d{1,2})\s*歲")
AGE_MIN = re.compile(r"(\d{1,2})\s*歲(?:或)?以上")
AGE_MAX = re.compile(r"(\d{1,2})\s*歲(?:或)?以下")


def parse_age(text: str) -> tuple[int | None, int | None]:
    """由對象／備註抽年齡範圍。抽唔到就 (None, None)＝不限／未列明。"""
    text = clean(text)
    if m := AGE_RANGE.search(text):
        return int(m.group(1)), int(m.group(2))
    if m := AGE_MIN.search(text):
        return int(m.group(1)), None
    if m := AGE_MAX.search(text):
        return None, int(m.group(1))
    # 常見學界字眼 → 粗略年齡
    if "中學生" in text or "中學" in text:
        return 12, 18
    if "大專" in text or "大學生" in text or "專上" in text:
        return 17, 25
    return None, None


FREE_WORDS = ["免費", "費用全免", "免收費", "free of charge", "無需付費"]
PAID_WORDS = ["費用：", "報名費", "學費", "收費", "$"]


def guess_fee(*texts: str) -> tuple[bool | None, str]:
    """(is_free, fee_text)。搵唔到線索就 (None, '未列明')。"""
    blob = " ".join(clean(t) for t in texts if t)
    low = blob.lower()
    for w in FREE_WORDS:
        if w.lower() in low:
            return True, "免費"
    for w in PAID_WORDS:
        if w.lower() in low:
            m = re.search(r"(?:費用|報名費|學費)[：:]\s*([^\s，,。;]+)", blob)
            return False, f"收費（{m.group(1)}）" if m else "收費"
    return None, "未列明"


MAINLAND = ["北京", "上海", "廣州", "深圳", "珠海", "東莞", "佛山", "中山", "內地", "大灣區",
            "酒泉", "西安", "杭州", "成都", "重慶", "福建", "廣東"]
OVERSEAS = ["海外", "日本", "韓國", "新加坡", "英國", "美國", "澳洲", "加拿大", "歐洲", "法國", "德國"]
GBA = ["大灣區", "廣州", "深圳", "珠海", "東莞", "佛山", "中山", "惠州", "江門", "肇慶"]


def guess_region(*texts: str) -> str:
    blob = " ".join(clean(t) for t in texts if t)
    if any(w in blob for w in OVERSEAS):
        return "海外"
    if any(w in blob for w in GBA):
        return "大灣區"
    if any(w in blob for w in MAINLAND):
        return "內地"
    if any(w in blob for w in ["網上", "線上", "Zoom", "網絡"]):
        return "網上"
    return "香港"


# ---------------------------------------------------------------- 統一資料格式

@dataclass
class Item:
    """所有來源都要 normalize 成呢個格式，前端只認呢啲欄位。"""
    id: str                       # 唯一 key（來源 + 原站 id）
    source: str                   # youth_gov / eventbrite / artmate ...
    source_label: str             # 顯示名：政府青少年網站
    source_type: str              # 政府 / 非牟利 / 活動平台
    title: str
    url: str                      # 原站詳情頁
    kind: str = "活動"             # 活動 / 計劃 / 課程 / 職位
    categories: list[str] = field(default_factory=list)   # 升學就業、創業…（由原站來）
    tags: list[str] = field(default_factory=list)
    organiser: str = ""
    venue: str = ""
    region: str = "香港"
    start_date: str | None = None
    end_date: str | None = None
    date_text: str = ""
    time_text: str = ""
    deadline: str | None = None
    audience: str = ""
    age_min: int | None = None
    age_max: int | None = None
    is_free: bool | None = None
    fee_text: str = "未列明"
    deposit: str = ""             # 有值＝要按金（例：HKD 50）
    apply_url: str = ""
    enquiry: str = ""
    summary: str = ""
    image: str = ""
    updated: str | None = None    # 原站最後更新日
    scraped_at: str = ""

    def finalize(self) -> dict:
        self.scraped_at = datetime.utcnow().date().isoformat()
        return asdict(self)
