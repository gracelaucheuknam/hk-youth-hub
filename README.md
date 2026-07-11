# 青年機會匯 · HK Youth Hub

自動抓取香港各機構嘅**青年活動／計劃／課程**，統一格式後喺一個網頁度篩選同搜尋。
零成本架構：GitHub Actions 每日跑 scraper → 生成 `events.json` → GitHub Pages 靜態前端讀取。

```
機構官網 ──► scrapers/*.py ──► build.py ──► docs/data/events.json ──► docs/index.html
                                  ▲                                       (GitHub Pages)
                          GitHub Actions 每日 06:00 (HKT)
```

## 快速開始

```bash
pip install -r requirements.txt
python build.py                 # 抓取所有來源，寫入 docs/data/events.json
cd docs && python -m http.server 8000
# 開 http://localhost:8000
```

> 前端用 `fetch()` 讀 JSON，所以**唔可以直接 double-click `index.html`**（file:// 會被 CORS 擋），要行上面個 http.server，或者直接上 GitHub Pages。

## 上線（GitHub Pages）

1. Push 上 GitHub。
2. Settings → Pages → Source 揀 `Deploy from a branch`，branch `main`，folder `/docs`。
3. Settings → Actions → General → Workflow permissions 揀 **Read and write**（Actions 要 commit 返 JSON）。
4. Actions 分頁按 `Run workflow` 手動試一次。

## 檔案結構

| 檔案 | 做咩 |
|---|---|
| `scrapers/base.py` | 共用工具：robots.txt 檢查、限速、重試、日期／年齡／費用／地區解析、`Item` 統一格式 |
| `scrapers/youth_gov.py` | 政府青少年網站（已完成，4 個板塊 + 詳情頁） |
| `scrapers/artmate.py` | art-mate 藝文平台（已完成，5 個標籤 × 3 頁 + 詳情頁，有票價／按金） |
| `scrapers/eventbrite.py` | Eventbrite 香港（已完成，讀搜尋頁內嵌 JSON，唔使入詳情頁） |
| `scrapers/erb.py` | ERB 課程（GraphQL；請求由 `scrapers/erb_request.json` 讀，見下） |
| `scrapers/estart.py` | 青年就業起點 Y.E.S.（課程／活動 + 招聘會，ASP.NET REST API） |
| `scrapers/manual.py` | 人手來源：讀 `data/manual.csv`（長期計劃，例如 YETP） |
| `scrapers/_template.py` | 新來源範本 |
| `build.py` | 跑所有 scraper、合併去重、寫 `events.json` + `meta.json` |
| `docs/index.html` | 前端（篩選選項由資料自動生成） |
| `.github/workflows/update-data.yml` | 每日自動更新 |

## 統一資料格式（`Item`）

```jsonc
{
  "id": "youth_gov:d4f866c5-…",     // 來源:原站 id，用嚟去重
  "source_label": "政府青少年網站",
  "source_type": "政府",             // 政府 / 非牟利 / 活動平台
  "title": "律政i-Day 2026",
  "url": "https://…",               // 原站詳情頁
  "kind": "活動",                    // 活動 / 計劃 / 課程 / 職位
  "categories": ["升學就業"],        // 用返原站嘅分類，前端自動生成篩選掣
  "tags": ["律政司", "律師"],
  "organiser": "律政司",
  "venue": "…律政中心…",
  "region": "香港",                  // 香港 / 大灣區 / 內地 / 海外 / 網上
  "start_date": "2026-07-13",
  "end_date": "2026-07-13",
  "time_text": "18:00 - 19:30",
  "deadline": null,
  "audience": "法律學生及其他大專生",
  "age_min": 17, "age_max": 25,      // 解析唔到就 null＝不限
  "is_free": null,                   // true / false / null（未列明）
  "apply_url": "https://…",          // 有就直接跳報名頁
  "image": "https://…",
  "delisted": false                  // 原站落咗架就標記，唔會即刻刪
}
```

## 加新來源（三步）

1. `cp scrapers/_template.py scrapers/artmate.py`，寫 `discover_urls()` 同 `parse_detail()`，全部 request 用 `polite_get()`。
2. 喺 `scrapers/__init__.py` 加返 `"artmate": artmate.scrape`。
3. `python build.py --only artmate` 試跑。前端唔使改，篩選掣會自己多咗新來源。

**建議次序（由易到難）：**

| 來源 | 狀態 | 備註 |
|---|---|---|
| youth.gov.hk | ✅ 完成 | |
| art-mate.net | ✅ 完成 | 標籤 `免費/工作坊/講座/課程/導賞`，可喺 `CRAWL_TAGS` 改 |
| ERB 課程 | ✅ 完成 | GraphQL persisted query（`/q`），已填好 `scrapers/erb_request.json` |
| Eventbrite HK | ✅ 完成 | 公開搜尋 API 已停用；改讀搜尋頁內嵌 `__SERVER_DATA__` JSON，有 JSON-LD 後備 |
| Y.E.S. (e-start) | ✅ 完成 | `/api/courses`；要先開 `/Course` 攞 session cookie + RequestVerificationToken |
| YETP (yes.labour) | 📄 用 CSV | 本質係長期計劃，寫入 `data/manual.csv` |
| SmartPlay | ❌ 放棄 | 真系統喺 `smartplay.lcsd.gov.hk`，SPA + 要「智方便」實名登入 |
| JC Fit City | 🚫 唔准抓 | robots.txt 明文禁止自動存取，唔會抓 |
| ~~bayarea / 勞工處 / Social Career / HKYouth+~~ | ❌ 已放棄 | |

## Scraper 壞咗點算

- `build.py` 抓到 **0 個項目**唔會清空舊資料，只會喺 log 出 `⚠ 可能原站改版`，`meta.json` 亦會記低。
- 每次寫入前會備份 `events.prev.json`。
- `youth_gov.py` 嘅 `_field()` 係靠**標籤文字**（「日期」「地點」「主辦機構」）搵欄位，唔靠 CSS class，所以原站改版式都多數唔會爆。

## 抓取守則（重要）

呢個 project 只做**索引同導流**，唔係複製內容：

- 每次 request 前檢查 `robots.txt`（`base.py` 自動做）。
- 每個 host 之間隔 1.5 秒，唔會拖冧人哋個網站。
- User-Agent 表明身分同聯絡方法 —— **記得改 `base.py` 入面嘅 `USER_AGENT`，填返你自己嘅 GitHub 同 email**。
- 只儲 metadata（標題、日期、地點、連結），描述最多截 280 字，每張卡都連結返原站。
- 版權屬各機構所有；政府資料一般准許非商業轉載，但仍要註明出處（前端 footer 已寫）。
- 唔好縮短輪詢週期（一日一次已經足夠），亦唔好繞過任何登入或防爬機制。


## ERB：`erb_request.json` 點運作

`course.erb.org` 用 **persisted query（APQ）**：client 唔會送 GraphQL query 文字，
只送 `operationName` + `sha256Hash`，server 自己查返條 query。所以 `erb_request.json`
入面唔會見到 query，只有個 hash：

```jsonc
{
  "url": "https://course.erb.org/q",          // POST
  "headers": { "Authorization": "Bearer ...", "lang": "TC", ... },
  "payload": {
    "operationName": "ERBCourseSearchListQuery",
    "variables": { "params": { "commence_date": "3", ... } },   // 3 = 3個月內開班
    "extensions": { "persistedQuery": { "sha256Hash": "d68a7ca6..." } }
  },
  "cursor_path": ["variables", "params", "cursor"]
}
```

- **想抓多啲／少啲**：改 `variables.params`（`commence_date` 1/2/3 個月、
  `categorys` 用 `erb_options.json` 入面嘅 code，例如 `["P","Y"]` = 就業掛鈎 + 青年培訓）
- **個 hash 失效時**（原站出新版）：log 會直接叫你重抄。返去
  `course.erb.org/searchlist?commence_date=3` → Network → 撳個 Response 有 `erbcourses`
  嘅 `/q` request → 「要求資料」→ copy 返落 `payload`。


## 人手來源（`data/manual.csv`）

長期計劃（YETP、Y.E.S.、ERB 課程類別…）唔係「活動流」，一年改一兩次，
唔值得寫 scraper，而且好多都係 SPA／要登入／robots 唔畀抓。

用 Excel 開 `data/manual.csv`，加一行就多一個項目（記得存做 **UTF-8 CSV**）：

- `categories` / `tags` 用「｜」分隔多個值
- `is_free`：TRUE / FALSE / 留空（＝未列明）
- 長期計劃唔使填日期，`date_text` 寫「全年接受申請」就得
- `kind`：活動 / 計劃 / 課程 —— 前端有得篩

改完行 `python build.py --only manual` 即刻見到效果。
