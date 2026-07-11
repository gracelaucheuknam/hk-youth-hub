"""Scraper registry：新增來源就 import 入嚟，再加入 SCRAPERS。"""
from . import youth_gov, artmate, eventbrite, erb, estart, manual

SCRAPERS = {
    "youth_gov": youth_gov.scrape,     # 政府青少年網站（活動）
    "artmate": artmate.scrape,         # art-mate 藝文平台（活動）
    "eventbrite": eventbrite.scrape,   # Eventbrite 香港（活動）
    "erb": erb.scrape,                 # ERB 課程（GraphQL persisted query）
    "estart": estart.scrape,           # 青年就業起點 Y.E.S.（課程／招聘會）
    "manual": manual.scrape,           # 人手維護：data/manual.csv（長期計劃）
}
