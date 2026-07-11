"""青年就業起點 Y.E.S.（e-start.gov.hk）—— 勞工處

課程／活動同招聘會嘅列表都係由 AJAX 攞返嚟：

    GET /api/courses?startDateTime=&endDateTime=&keyword=&courseTypeCD=&centerID=&statusCD=

呢個 endpoint 要三樣嘢：
    1. ASP.NET session cookie（開一次 /Course 就會 set）
    2. RequestVerificationToken（喺 /Course 個 HTML 入面）
    3. X-Requested-With: XMLHttpRequest

所以流程係：先開 /Course 攞 cookie + token → 再叫 API。
（token 每個 session 唔同，寫死冇用。）

⚠ 回應嘅欄位名我未見過實物，所以 _norm() 用「多個候選名」去砌。
   第一次跑會喺 log 印晒真實欄位名，唔啱嘅話貼返 log 就改得到。
"""
from __future__ import annotations

import re
import json
import logging

from bs4 import BeautifulSoup

from .base import Item, polite_get, clean, parse_date, parse_age, guess_region

log = logging.getLogger(__name__)

SOURCE = "estart"
SOURCE_LABEL = "青年就業起點 Y.E.S."
SOURCE_TYPE = "政府"
BASE = "https://www.e-start.gov.hk"

PAGES = {                       # 攞 token 用嘅版 → 對應 API
    "課程／活動": ("/Course", "/api/courses"),
    "招聘會": ("/JobFair", "/api/jobfairs"),      # 未證實，404 就自動跳過
}
API_QS = "?startDateTime=&endDateTime=&keyword=&courseTypeCD=&centerID=&statusCD="

TOKEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')


def _get_token(page_path: str) -> str | None:
    """開頁面攞 antiforgery token（順便 set 咗 session cookie）。"""
    html = polite_get(BASE + page_path)
    if not html:
        return None
    if m := TOKEN_RE.search(html):
        return m.group(1)
    soup = BeautifulSoup(html, "html.parser")
    for sel in ('input[name="__RequestVerificationToken"]',
                'meta[name="__RequestVerificationToken"]'):
        el = soup.select_one(sel)
        if el and (el.get("value") or el.get("content")):
            return el.get("value") or el.get("content")
    log.warning("[%s] %s 搵唔到 RequestVerificationToken，照試叫 API", SOURCE, page_path)
    return None


def _pick(row: dict, *names: str, default: str = "") -> str:
    """欄位名唔肯定，逐個候選試（大細楷都唔理）。"""
    lower = {k.lower(): v for k, v in row.items()}
    for n in names:
        v = lower.get(n.lower())
        if v not in (None, "", []):
            return clean(str(v))
    return default


def _norm(row: dict, kind: str) -> Item | None:
    title = _pick(row, "courseName", "courseNameTC", "name", "title",
                  "jobFairName", "eventName")
    if not title:
        return None

    cid = _pick(row, "courseID", "courseId", "id", "jobFairID", "code") or title
    start_raw = _pick(row, "startDateTime", "startDate", "courseStartDate", "fromDate")
    end_raw = _pick(row, "endDateTime", "endDate", "courseEndDate", "toDate")
    start = parse_date(start_raw)
    end = parse_date(end_raw) or start

    venue = _pick(row, "centerName", "center", "venue", "location", "centerNameTC")
    ctype = _pick(row, "courseTypeName", "courseType", "courseTypeCD", "type")
    status = _pick(row, "statusName", "status", "statusCD")
    quota = _pick(row, "quota", "vacancy", "places")
    summary = _pick(row, "description", "courseDescription", "content", "remarks")[:280]
    audience = _pick(row, "targetParticipant", "target", "eligibility")

    st = re.search(r"\d{1,2}:\d{2}", start_raw)
    et = re.search(r"\d{1,2}:\d{2}", end_raw)
    time_text = " - ".join(m.group(0) for m in (st, et) if m)

    age_min, age_max = parse_age(audience or title)
    if age_min is None:                 # Y.E.S. 服務對象本身就係 15–29 歲
        age_min, age_max = 15, 29

    cats = ["就業"] if kind == "招聘會" else ["就業", "進修"]

    return Item(
        id=f"{SOURCE}:{cid}",
        source=SOURCE,
        source_label=SOURCE_LABEL,
        source_type=SOURCE_TYPE,
        title=title,
        url=BASE + ("/JobFair" if kind == "招聘會" else "/Course"),
        kind="活動" if kind == "招聘會" else "課程",
        categories=cats,
        tags=[t for t in (ctype, status, kind) if t],
        organiser="勞工處 青年就業起點",
        venue=venue,
        region=guess_region(venue),
        start_date=start,
        end_date=end,
        date_text=clean(f"{start_raw} {('～ ' + end_raw) if end_raw and end_raw != start_raw else ''}"),
        time_text=time_text,
        audience=audience or "15至29歲青年",
        age_min=age_min,
        age_max=age_max,
        is_free=True,                   # Y.E.S. 所有課程／活動免費
        fee_text="免費",
        apply_url=BASE + "/MembershipIntro",
        enquiry="enquiry@e-start.gov.hk",
        summary=summary + (f"（名額 {quota}）" if quota else ""),
    )


def _fetch(api_path: str, token: str | None) -> list[dict]:
    headers = {
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": BASE + "/Course",
    }
    if token:
        headers["RequestVerificationToken"] = token

    body = polite_get(BASE + api_path + API_QS, headers=headers, allow_404=True)
    if not body:
        log.warning("[%s] %s 冇回應（可能唔存在），跳過", SOURCE, api_path)
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        log.error("[%s] %s 回嘅唔係 JSON（可能 token 失效或者被踢返去登入頁）",
                  SOURCE, api_path)
        return []

    for key in ("data", "result", "items", "courses", "records"):
        if isinstance(data, dict) and isinstance(data.get(key), list):
            return data[key]
    return data if isinstance(data, list) else []


def scrape() -> list[dict]:
    items: dict[str, dict] = {}
    for kind, (page, api) in PAGES.items():
        token = _get_token(page)
        rows = _fetch(api, token)
        if not rows:
            continue

        log.info("[%s] %s：攞到 %d 筆；欄位＝%s",
                 SOURCE, kind, len(rows), list(rows[0].keys())[:20])

        for row in rows:
            try:
                it = _norm(row, kind)
                if it:
                    items[it.id] = it.finalize()
            except Exception as e:  # noqa: BLE001
                log.exception("[%s] parse 失敗：%s", SOURCE, e)

    log.info("[%s] 成功抓到 %d 個項目", SOURCE, len(items))
    return list(items.values())
