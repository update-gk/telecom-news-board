"""
スマホ・通信業界 速報ボード用 - RSS取得スクリプト

ケータイWatch / ITmedia Mobile のRSSを取得し、カテゴリ・キャリアを自動判定した上で
data/news.json に書き出す。GitHub Actionsから定期実行されることを想定。

依存: feedparser (requirements.txt でインストール)
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "news.json"

# 取得元の設定。ITmedia Mobileはタイトルに"[ITmedia Mobile]"が付くITmedia全体RSSから
# 絞り込む方式(ITmedia側にモバイル専用RSSが見当たらないため)。
# docomo/auはキャリア公式のRSS配信。ソフトバンク/楽天モバイル/ワイモバイル/UQ mobileは
# 確実なRSS配信元が見つかっていないため未対応(見つかり次第追加)。
SOURCES = {
    "ktai": {
        "name": "ケータイWatch",
        "url": "https://k-tai.watch.impress.co.jp/data/rss/1.0/ktw/feed.rdf",
        "title_filter": None,
    },
    "itmedia": {
        "name": "ITmedia Mobile",
        "url": "https://rss.itmedia.co.jp/rss/2.0/itmedia_all.xml",
        "title_filter": lambda title: "ITmedia Mobile" in title,
    },
    "docomo": {
        "name": "NTTドコモ",
        "url": "https://www.docomo.ne.jp/info/rss/whatsnew.rdf",
        "title_filter": None,
    },
    "au": {
        "name": "au/KDDI",
        "url": "https://newsroom.kddi.com/news/newsrelease.xml",
        "title_filter": None,
    },
}

# カテゴリ判定ルール(上から順に一致したものを採用)
CATEGORY_RULES = [
    ("trouble", "障害・不具合", ["障害", "不具合", "つながらない", "休止", "メンテナンス", "復旧"]),
    ("price", "料金プラン", ["料金", "プラン", "値下げ", "値上げ", "月額", "改定"]),
    ("campaign", "キャンペーン", ["キャンペーン", "還元", "ポイント", "割引", "セール", "特典"]),
    ("mvno", "MVNO・格安SIM", ["格安", "MVNO", "SIM", "povo", "LINEMO", "ahamo"]),
    ("device", "端末", ["iPhone", "Android", "Pixel", "Galaxy", "Xperia", "AQUOS", "発売", "スマートフォン"]),
]

CARRIER_RULES = [
    ("ドコモ", ["ドコモ", "NTTドコモ", "ahamo"]),
    ("au/KDDI", ["au", "KDDI", "povo"]),
    ("ソフトバンク", ["ソフトバンク", "SoftBank", "LINEMO"]),
    ("楽天モバイル", ["楽天モバイル", "楽天"]),
    ("Y!mobile", ["ワイモバイル", "Y!mobile"]),
    ("UQ mobile", ["UQ mobile", "UQモバイル"]),
]

TITLE_PREFIX_RE = re.compile(r"^\[.*?\]\s*")


def categorize(title: str):
    for key, label, words in CATEGORY_RULES:
        if any(w in title for w in words):
            return key, label
    return "other", "その他"


def find_carrier(title: str):
    for label, words in CARRIER_RULES:
        if any(w in title for w in words):
            return label
    return None


def parse_date(entry) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def fetch_source(source_key: str, config: dict) -> list[dict]:
    feed = feedparser.parse(config["url"])
    articles = []
    for entry in feed.entries:
        raw_title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not raw_title or not link:
            continue
        if config["title_filter"] and not config["title_filter"](raw_title):
            continue

        title = TITLE_PREFIX_RE.sub("", raw_title)
        cat_key, cat_label = categorize(title)
        carrier = find_carrier(title)
        date = parse_date(entry)

        articles.append(
            {
                "id": f"{source_key}-{link}",
                "title": title,
                "link": link,
                "date": date.isoformat(),
                "sourceKey": source_key,
                "catKey": cat_key,
                "catLabel": cat_label,
                "carrier": carrier,
            }
        )
    return articles


def main():
    all_articles: list[dict] = []
    errors: list[str] = []

    for source_key, config in SOURCES.items():
        try:
            all_articles.extend(fetch_source(source_key, config))
        except Exception as exc:  # noqa: BLE001 - 取得失敗はログに残して継続
            errors.append(f"{config['name']}: {exc}")

    all_articles.sort(key=lambda a: a["date"], reverse=True)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "errors": errors,
                "articles": all_articles,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"{len(all_articles)} 件の記事を {OUTPUT_PATH} に書き出しました。")
    if errors:
        print("取得に失敗した情報源:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
