"""
スマホ・通信業界 速報ボード用 - ニュース取得スクリプト

以下の2方式で各社の最新情報を集め、カテゴリ・キャリアを自動判定して
data/news.json に書き出す。GitHub Actionsから定期実行されることを想定。

  1. RSS      : ケータイWatch / ITmedia Mobile / NTTドコモ / au(KDDI)
  2. スクレイピング: ソフトバンク / 楽天モバイル / Y!mobile / UQ mobile
                (いずれも公式RSSが確認できないため、公開ページ/JSON APIから取得)

依存: feedparser / requests / beautifulsoup4 (requirements.txt でインストール)
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "news.json"

JST = timezone(timedelta(hours=9))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 telecom-news-board/1.0"
)
HTTP_TIMEOUT = 20
MAX_ITEMS_PER_SOURCE = 30

# 見出し画像(OGP)。記事ページごとに1枚だけ持つメディアのみ対象。
# キャリア公式はどの記事も同じロゴOGPなので取得せず、表示側でブランドバッジを出す。
IMAGE_SOURCES = {"ktai", "itmedia"}
MAX_IMAGE_FETCHES = 70          # 1回の実行で新規に取りに行く上限
MAX_IMAGE_BYTES = 600_000       # これを超える画像はサムネイルに重いので不採用

# RSS で取得できる情報源。ITmedia Mobileはタイトルに"ITmedia Mobile"が付く
# ITmedia全体RSSから絞り込む方式(モバイル専用RSSが見当たらないため)。
RSS_SOURCES = {
    "ktai": {
        "name": "ケータイWatch",
        "url": "https://k-tai.watch.impress.co.jp/data/rss/1.0/ktw/feed.rdf",
        "title_filter": None,
        "carrier": None,
    },
    "itmedia": {
        "name": "ITmedia Mobile",
        "url": "https://rss.itmedia.co.jp/rss/2.0/itmedia_all.xml",
        "title_filter": lambda title: "ITmedia Mobile" in title,
        "carrier": None,
    },
    "docomo": {
        "name": "NTTドコモ",
        "url": "https://www.docomo.ne.jp/info/rss/whatsnew.rdf",
        "title_filter": None,
        "carrier": "ドコモ",
    },
    "au": {
        "name": "au/KDDI",
        "url": "https://newsroom.kddi.com/news/newsrelease.xml",
        "title_filter": None,
        "carrier": "au/KDDI",
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
JP_DATE_RE = re.compile(r"(\d{4})\D{1,2}(\d{1,2})\D{1,2}(\d{1,2})")
COMPACT_DATE_RE = re.compile(r"\b(\d{4})(\d{2})(\d{2})\b")


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


def parse_rss_date(entry) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def parse_jp_date(text: str) -> datetime:
    """'2026年8月21日' / '2026.07.29' / '2026/08/27 10:00:00' などを JST の datetime に。"""
    text = text or ""
    match = JP_DATE_RE.search(text) or COMPACT_DATE_RE.search(text)
    if not match:
        return datetime.now(timezone.utc)
    year, month, day = (int(g) for g in match.groups())
    try:
        return datetime(year, month, day, tzinfo=JST)
    except ValueError:
        return datetime.now(timezone.utc)


def build_article(source_key: str, source_carrier, title: str, link: str, date: datetime) -> dict:
    title = TITLE_PREFIX_RE.sub("", title).strip()
    cat_key, cat_label = categorize(title)
    carrier = find_carrier(title) or source_carrier
    return {
        "id": f"{source_key}-{link}",
        "title": title,
        "link": link,
        "date": date.astimezone(timezone.utc).isoformat(),
        "sourceKey": source_key,
        "catKey": cat_key,
        "catLabel": cat_label,
        "carrier": carrier,
    }


# --------------------------------------------------------------------------- RSS


def fetch_rss(source_key: str, config: dict) -> list[dict]:
    feed = feedparser.parse(config["url"])
    articles = []
    for entry in feed.entries:
        raw_title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not raw_title or not link:
            continue
        if config["title_filter"] and not config["title_filter"](raw_title):
            continue
        articles.append(
            build_article(
                source_key,
                config["carrier"],
                raw_title,
                link,
                parse_rss_date(entry),
            )
        )
    return articles


# ------------------------------------------------------------------- スクレイピング


def _http_get(url: str) -> requests.Response:
    res = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
    res.raise_for_status()
    return res


def _soup(url: str) -> BeautifulSoup:
    res = _http_get(url)
    res.encoding = res.apparent_encoding or res.encoding
    return BeautifulSoup(res.text, "html.parser")


def _abs(base: str, link: str) -> str:
    if link.startswith("http"):
        return link
    return base.rstrip("/") + "/" + link.lstrip("/")


def scrape_softbank() -> list[dict]:
    """ソフトバンク(株)のプレスリリース。公開JSON APIから取得。"""
    url = (
        "https://www.softbank.jp/scsystem/api/CreateJson/"
        "?category=corp&sub_category=sbkk_press_top&language=ja-JP&end_line=40"
    )
    data = _http_get(url).json()
    articles = []
    for month in data.get("data", []):
        for item in month.get("list", []):
            title = (item.get("title") or "").strip()
            raw = (item.get("url") or "").strip()
            if not title or not raw:
                continue
            link = _abs("https://www.softbank.jp", raw)
            date = parse_jp_date(item.get("date") or item.get("display_date") or "")
            articles.append(build_article("softbank", "ソフトバンク", title, link, date))
    return articles


def scrape_rakuten() -> list[dict]:
    """楽天モバイル(楽天モバイル株式会社)のニュース。プレスリリース+お知らせ。"""
    base = "https://corp.mobile.rakuten.co.jp"
    soup = _soup(f"{base}/news/")
    articles = []
    for dl in soup.select("dl.js-news-Headlines"):
        for row in dl.select("div[data-tag]"):
            dt = row.find("dt")
            anchor = row.select_one("dd a")
            if not dt or not anchor:
                continue
            title = anchor.get_text(strip=True)
            link = _abs(base, anchor.get("href", ""))
            if not title or not anchor.get("href"):
                continue
            articles.append(
                build_article("rakuten", "楽天モバイル", title, link, parse_jp_date(dt.get_text()))
            )
    return articles


def scrape_ymobile() -> list[dict]:
    """Y!mobile公式サイトの新着情報。"""
    base = "https://www.ymobile.jp"
    soup = _soup(f"{base}/info/")
    scope = soup.select_one("div.tab-target-item.is-active") or soup
    articles = []
    for li in scope.select("ul.list-info li.list-info-item"):
        anchor = li.find("a")
        if not anchor:
            continue
        text_el = anchor.select_one("p.list-info-text")
        title = (text_el.get_text(strip=True) if text_el else anchor.get_text(" ", strip=True)).strip()
        href = anchor.get("href", "")
        if not title or not href:
            continue
        link = _abs(base, href)
        date_text = anchor.get("datetime") or ""
        anchor_date = anchor.select_one("span.list-info-date")
        if not date_text and anchor_date:
            date_text = anchor_date.get_text(strip=True)
        articles.append(
            build_article("ymobile", "Y!mobile", title, link, parse_jp_date(date_text))
        )
    return articles


def scrape_uq() -> list[dict]:
    """UQ mobile / UQ WiMAX のニュースリリース。"""
    base = "https://www.uqwimax.jp"
    soup = _soup(f"{base}/annai/news_release/")
    articles = []
    for li in soup.select("ul.listNewsIn > li"):
        dt = li.find("dt")
        anchor = li.find("a")
        if not dt or not anchor:
            continue
        title = anchor.get_text(strip=True)
        href = anchor.get("href", "")
        if not title or not href:
            continue
        link = _abs(base, href)
        articles.append(
            build_article("uq", "UQ mobile", title, link, parse_jp_date(dt.get_text()))
        )
    return articles


SCRAPER_SOURCES = {
    "softbank": {"name": "ソフトバンク", "fetch": scrape_softbank},
    "rakuten": {"name": "楽天モバイル", "fetch": scrape_rakuten},
    "ymobile": {"name": "Y!mobile", "fetch": scrape_ymobile},
    "uq": {"name": "UQ mobile", "fetch": scrape_uq},
}


# ------------------------------------------------------------------- 見出し画像


def _og_image_url(page_url: str) -> str | None:
    """記事ページから og:image / twitter:image を1枚拾う。https のみ。"""
    res = requests.get(page_url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
    res.raise_for_status()
    res.encoding = res.apparent_encoding or res.encoding
    soup = BeautifulSoup(res.text, "html.parser")
    candidates = [
        ("meta", {"property": "og:image"}),
        ("meta", {"name": "twitter:image"}),
        ("meta", {"name": "twitter:image:src"}),
    ]
    for name, attrs in candidates:
        tag = soup.find(name, attrs=attrs)
        src = (tag.get("content") if tag else "") or ""
        src = src.strip()
        if src.startswith("http://"):
            src = "https://" + src[len("http://") :]
        if src.startswith("https://"):
            return src
    return None


def _image_ok(image_url: str) -> bool:
    """サムネイルとして許容できるサイズ・種別かを HEAD で確認。"""
    try:
        head = requests.head(
            image_url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT, allow_redirects=True
        )
        if not head.ok:
            return False
        ctype = head.headers.get("Content-Type", "")
        if ctype and not ctype.lower().startswith("image/"):
            return False
        length = head.headers.get("Content-Length")
        if length is None:
            return False
        return int(length) <= MAX_IMAGE_BYTES
    except Exception:  # noqa: BLE001
        return False


def _fetch_one_image(page_url: str) -> str | None:
    try:
        url = _og_image_url(page_url)
    except Exception:  # noqa: BLE001
        return None
    if url and _image_ok(url):
        return url
    return None


def _load_previous_images() -> dict[str, str]:
    if not OUTPUT_PATH.exists():
        return {}
    try:
        data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return {
        a["id"]: a["image"]
        for a in data.get("articles", [])
        if a.get("id") and a.get("image")
    }


def enrich_images(articles: list[dict]) -> None:
    """対象メディアの記事に image を付与。前回分は再利用し、新規のみ取りに行く。"""
    previous = _load_previous_images()
    to_fetch: list[dict] = []
    budget = MAX_IMAGE_FETCHES

    for article in articles:
        article.setdefault("image", None)
        if article["sourceKey"] not in IMAGE_SOURCES:
            continue
        if article["id"] in previous:
            article["image"] = previous[article["id"]]
        elif budget > 0:
            budget -= 1
            to_fetch.append(article)

    if not to_fetch:
        return

    got = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_fetch_one_image, a["link"]): a for a in to_fetch}
        for future in as_completed(futures):
            article = futures[future]
            try:
                article["image"] = future.result()
                if article["image"]:
                    got += 1
            except Exception:  # noqa: BLE001
                article["image"] = None

    print(f"見出し画像: {got}/{len(to_fetch)} 件取得(前回再利用 {len(previous)} 件)")


# -------------------------------------------------------------------------- main


def _dedupe_and_trim(articles: list[dict]) -> list[dict]:
    articles.sort(key=lambda a: a["date"], reverse=True)
    seen: set[str] = set()
    per_source: dict[str, int] = {}
    result = []
    for article in articles:
        if article["id"] in seen:
            continue
        seen.add(article["id"])
        key = article["sourceKey"]
        per_source[key] = per_source.get(key, 0) + 1
        if per_source[key] > MAX_ITEMS_PER_SOURCE:
            continue
        result.append(article)
    return result


def main():
    all_articles: list[dict] = []
    errors: list[str] = []

    for source_key, config in RSS_SOURCES.items():
        try:
            all_articles.extend(fetch_rss(source_key, config))
        except Exception as exc:  # noqa: BLE001 - 取得失敗はログに残して継続
            errors.append(f"{config['name']} (RSS): {exc}")

    for source_key, config in SCRAPER_SOURCES.items():
        try:
            fetched = config["fetch"]()
            if not fetched:
                errors.append(f"{config['name']} (scrape): 0件。ページ構造が変わった可能性")
            all_articles.extend(fetched)
        except Exception as exc:  # noqa: BLE001 - 同上
            errors.append(f"{config['name']} (scrape): {exc}")

    all_articles = _dedupe_and_trim(all_articles)
    enrich_images(all_articles)

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
        print("取得に問題があった情報源:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
