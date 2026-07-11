"""僱員再培訓局 ERB 課程（course.erb.org）

⚠ 佢用 persisted query（APQ）：client 只送 operationName + sha256Hash，唔送 query 文字。
   所以 erb_request.json 個 payload 要原封不動抄返個 request body，例如：

     {"operationName": "...", "variables": {...},
      "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "..."}}}

   scraper 翻頁時只會改 variables.cursor，其餘唔郁。
   原站出新版時個 hash 會變，到時 log 會叫你重抄一次。


原站係 React SPA，課程資料由 GraphQL 攞返嚟：
    data.erbcourses = { cursor, hasMore, searchKey, records[] }
    records[].course = { id, ref, name, ind_grp（行業）, options.types[]（課程類別） }

因為 GraphQL 個 query 同 endpoint 唔喺 HTML 入面，所以呢個 scraper 唔寫死請求，
而係讀同一個資料夾嘅 erb_request.json。原站日後改 query，改個 JSON 就得，
唔使改 code。

erb_request.json 格式：
{
  "url": "https://course.erb.org/....",          ← XHR 個 Request URL
  "headers": {"content-type": "application/json"},
  "payload": { "query": "...", "variables": {...} },   ← 個 Request Payload 原封不動
  "cursor_path": ["variables", "cursor"],        ← payload 入面邊個位放 cursor（分頁用）
  "course_url_template": "https://course.erb.org/course/{id}"
}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import quote

from .base import Item, polite_post, clean

log = logging.getLogger(__name__)

SOURCE = "erb"
SOURCE_LABEL = "僱員再培訓局 ERB"
SOURCE_TYPE = "政府"
CONFIG = Path(__file__).parent / "erb_request.json"
OPTIONS = json.loads((Path(__file__).parent / "erb_options.json").read_text("utf-8"))
MAX_PAGES = 60                # 800+ 課程 ÷ 每頁 20 ≈ 45 頁，留啲餘裕

# 課程類別 → 費用（ERB 官方安排）
FEE_BY_TYPE = {
    "就業掛鈎課程": (True, "學費全免（七天或以上設再培訓津貼）"),
    "青年培訓課程": (None, "部分免費／部分資助"),
    "技能提升課程": (False, "收費（合資格人士可申請學費豁免或資助）"),
    "通用技能課程": (False, "收費（合資格人士可申請學費豁免或資助）"),
    "特定服務對象課程": (None, "視課程而定"),
    "殘疾及工傷康復人士課程": (None, "視課程而定"),
}


def _label(group: str, code: str) -> str:
    """由 code 還原中文，例如 Districts 3300 → 沙田區。"""
    return OPTIONS.get(group, {}).get(str(code), str(code))


def _load_config() -> dict | None:
    if not CONFIG.exists():
        log.error("搵唔到 %s —— 請由 DevTools 抄返 ERB 個 GraphQL 請求（見 README）",
                  CONFIG.name)
        return None
    return json.loads(CONFIG.read_text("utf-8"))


def _set_cursor(payload: dict, path: list[str], cursor: str | None) -> None:
    node = payload
    for k in path[:-1]:
        node = node.setdefault(k, {})
    node[path[-1]] = cursor


def _to_item(course: dict, url_tpl: str) -> Item | None:
    cid = clean(course.get("id") or course.get("ref") or "")
    name = clean(course.get("name") or "")
    if not (cid and name):
        return None

    opts = course.get("options") or {}
    types = [clean(t.get("label") or _label("Categorys", t.get("value", "")))
             for t in (opts.get("types") or []) if t.get("label") or t.get("value")]
    industry = clean(course.get("ind_grp") or "")

    # 有啲 response 會多返呢啲欄位；冇就自動略過
    districts = [clean(d.get("label") or _label("Districts", d.get("value", "")))
                 for d in (opts.get("districts") or []) if d]
    modes = [clean(m.get("label") or _label("Modes", m.get("value", "")))
             for m in (opts.get("modes") or []) if m]
    qr = clean(str(course.get("qr_level") or ""))

    is_free, fee_text = (None, "視課程而定")
    for t in types:
        if t in FEE_BY_TYPE:
            is_free, fee_text = FEE_BY_TYPE[t]
            break

    return Item(
        id=f"{SOURCE}:{cid}",
        source=SOURCE,
        source_label=SOURCE_LABEL,
        source_type=SOURCE_TYPE,
        title=name,
        url=url_tpl.format(id=quote(cid), ref=quote(str(course.get("ref", cid))),
                           name=quote(name)),
        kind="課程",
        categories=(types or ["進修"]) + ["進修"],
        tags=[t for t in ([industry] + districts + modes +
                          ([_label("Qrlevels", qr)] if qr else [])) if t],
        organiser="ERB 委任培訓機構",
        venue="",
        region="香港",
        start_date=None,             # 只抓「已有暫定開班日期」嘅課程，實際日期見原站
        end_date=None,
        date_text="已有暫定開班日期",
        audience="15歲或以上香港合資格僱員",
        age_min=15,
        age_max=None,
        is_free=is_free,
        fee_text=fee_text,
        summary=f"行業範疇：{industry}" if industry else "",
    )


def scrape() -> list[dict]:
    cfg = _load_config()
    if not cfg:
        return []

    url = cfg["url"]
    headers = cfg.get("headers") or {"Content-Type": "application/json; charset=utf-8"}
    if "Authorization" not in headers:
        log.warning("[%s] config 冇 Authorization header，ERB 可能會回 401", SOURCE)
    payload = json.loads(json.dumps(cfg["payload"]))      # deep copy
    cursor_path = cfg.get("cursor_path", ["variables", "cursor"])
    searchkey_path = cfg.get("searchkey_path")          # 可選
    url_tpl = cfg.get("course_url_template", "https://course.erb.org/search")

    items: dict[str, dict] = {}
    cursor = None

    search_key = None
    for page in range(1, MAX_PAGES + 1):
        if page > 1:                       # 第一頁唔好放 cursor，同瀏覽器一致
            _set_cursor(payload, cursor_path, cursor)
            if searchkey_path and search_key:
                _set_cursor(payload, searchkey_path, search_key)
        data = polite_post(url, payload, headers)
        if not data:
            break
        if data.get("errors"):
            codes = {(e.get("extensions") or {}).get("code") for e in data["errors"]}
            if "PERSISTED_QUERY_NOT_FOUND" in codes or any(
                    "PersistedQueryNotFound" in str(e) for e in data["errors"]):
                log.error("[%s] 個 sha256Hash 過期咗（原站出咗新版）。"
                          "重新由 DevTools 抄一次 erb_request.json 個 payload 就得。", SOURCE)
            else:
                log.error("[%s] GraphQL 回錯誤：%s", SOURCE, data["errors"])
            break

        conn = (data.get("data") or {}).get("erbcourses") or {}
        records = conn.get("records") or []
        if not records:
            break

        before = len(items)
        for rec in records:
            try:
                it = _to_item(rec.get("course") or {}, url_tpl)
                if it:
                    items[it.id] = it.finalize()
            except Exception as e:  # noqa: BLE001
                log.exception("parse 失敗：%s", e)

        log.info("[%s] 第 %d 頁 → 新增 %d 個（累計 %d）",
                 SOURCE, page, len(items) - before, len(items))

        cursor = conn.get("cursor")
        search_key = conn.get("searchKey") or search_key

        if len(items) == before and page > 1:
            log.error("[%s] 第 %d 頁冇新課程 —— cursor 可能塞錯位置。"
                      "試下改 erb_request.json 個 cursor_path（例如 [\"variables\",\"cursor\"]）",
                      SOURCE, page)
            break
        if not conn.get("hasMore") or not cursor:
            break

    log.info("[%s] 成功抓到 %d 個課程", SOURCE, len(items))
    return list(items.values())
