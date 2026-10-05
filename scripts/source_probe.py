#!/usr/bin/env python3
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 16; Mobile) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SESSION.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=2,
            connect=2,
            read=2,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
        )
    ),
)

SOURCES = [
    {
        "name": "まるまる丸 敦賀",
        "kind": "charter",
        "url": "https://marumarumaru.co.jp/report/",
        "detail_patterns": [r"/report/", r"instagram"],
    },
    {
        "name": "心友丸 越前",
        "kind": "charter",
        "url": "https://www.shinyuumaru.com/contents/information.php",
        "detail_patterns": [r"information", r"contents"],
    },
    {
        "name": "MIYAMOTOMARU2 舞鶴",
        "kind": "charter",
        "url": "https://ameblo.jp/miyamotomar/",
        "detail_patterns": [r"/entry-\d+\.html"],
    },
    {
        "name": "小浜マリーナ",
        "kind": "marina",
        "url": "https://www.obama-marina.com/catch/index.php",
        "detail_patterns": [r"/catch/", r"index\.php"],
    },
    {
        "name": "福丸 小浜",
        "kind": "charter",
        "url": "https://www.e-fukumaru.com/",
        "detail_patterns": [r"/choka", r"/catch", r"/blog", r"/news"],
    },
    {
        "name": "SUPER VIKING 小浜",
        "kind": "charter_aggregator",
        "url": "https://reserve.castingnet.jp/ship00107c.html",
        "detail_patterns": [r"ship00107", r"choka"],
    },
    {
        "name": "あみや渡船 若狭大島",
        "kind": "raft",
        "url": "https://www.fishing-v.jp/choka/choka_detail.php?s=582",
        "detail_patterns": [r"choka_detail\.php"],
    },
    {
        "name": "ヴィーナス 丹後",
        "kind": "charter",
        "url": "https://www.fisher-venus.com/chouka/",
        "detail_patterns": [r"/chouka/"],
    },
    {
        "name": "オールブルー 丹後",
        "kind": "charter",
        "url": "https://www.allbluemarine.com/",
        "detail_patterns": [r"chouka", r"blog", r"2026"],
    },
    {
        "name": "ちどり丸 久美浜",
        "kind": "charter_aggregator",
        "url": "https://www.fishing-v.jp/choka/choka_detail.php?s=1748",
        "detail_patterns": [r"choka_detail\.php"],
    },
    {
        "name": "ANGLERS 若狭湾",
        "kind": "catch_platform",
        "url": "https://anglers.jp/areas/460/fishes/103",
        "detail_patterns": [r"/catches/\d+"],
    },
    {
        "name": "カンパリ 舞鶴東部",
        "kind": "catch_platform",
        "url": "https://fishing.ne.jp/fishingpost/area/maiduru-tobu?fish=fish-aoriika",
        "detail_patterns": [r"/fishingpost/\d+"],
    },
    {
        "name": "カンパリ 敦賀東部",
        "kind": "catch_platform",
        "url": "https://fishing.ne.jp/fishingpost/area/turuga-tobu?fish=fish-aoriika",
        "detail_patterns": [r"/fishingpost/\d+"],
    },
    {
        "name": "上州屋",
        "kind": "tackle_shop",
        "url": "https://www.johshuya.co.jp/shop/choka.php?s=151",
        "detail_patterns": [r"choka\.php\?s=\d+.*", r"/shop/choka/"],
    },
    {
        "name": "FISHERS",
        "kind": "tackle_shop",
        "url": "https://www.fishers.co.jp/",
        "detail_patterns": [r"/shopinfo/page\.html"],
    },
    {
        "name": "ブンブン釣行記",
        "kind": "tackle_shop_media",
        "url": "https://bunbun-fishing.com/fishing/",
        "detail_patterns": [r"/fishing/\d+"],
    },
    {
        "name": "TRITON 舞鶴",
        "kind": "charter",
        "url": "https://triton-maizuru.com/topics.html",
        "detail_patterns": [r"topics", r"blog", r"\d{4}"],
    },
    {
        "name": "すばる 丹後",
        "kind": "charter",
        "url": "https://subarutango.jimdofree.com/",
        "detail_patterns": [r"/\d{4}/\d{2}/", r"blog"],
    },
    {
        "name": "OCEANS 丹後",
        "kind": "charter",
        "url": "https://oceans2009.com/tyoka",
        "detail_patterns": [r"tyoka", r"blog", r"\d{4}"],
    },
    {
        "name": "シーマン 丹後",
        "kind": "charter",
        "url": "https://seaman-tango.com/blog_articles/",
        "detail_patterns": [r"/blog_articles/\d+"],
    },
]

DATE_PATTERNS = [
    re.compile(r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}"),
    re.compile(r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日"),
]
DEPTH_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*(?:m|Ｍ|メートル)(?![a-zA-Z])", re.I)
RANGE_RE = re.compile(r"(?<!\d)(\d{1,3})\s*(?:m|Ｍ)?\s*[〜~～\-]\s*(\d{1,3})\s*(?:m|Ｍ)", re.I)

AORI_WORDS = ("アオリ", "アオリイカ", "ティップラン", "エギング", "エギ")
NEGATIVE_WORDS = ("ボウズ", "坊主", "釣れない", "釣れず", "反応なし", "渋い", "厳しい", "チェイス")
CONTEXT_WORDS = ("水深", "ボトム", "中層", "表層", "浅場", "深場", "レンジ", "タナ")


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def unique_matches(patterns, text):
    out = []
    for p in patterns:
        out.extend(p.findall(text))
    return out


def probe(source):
    item = {
        "name": source["name"],
        "kind": source["kind"],
        "url": source["url"],
        "checked_at": NOW.isoformat(timespec="seconds"),
    }
    try:
        r = SESSION.get(source["url"], timeout=(6, 16), allow_redirects=True)
        item["http_status"] = r.status_code
        item["final_url"] = r.url
        item["bytes"] = len(r.content)
        item["content_type"] = r.headers.get("content-type", "")
        r.raise_for_status()

        soup = BeautifulSoup(r.content, "html.parser")
        title = clean(soup.title.get_text(" ", strip=True) if soup.title else "")
        text = clean(soup.get_text(" ", strip=True))
        links = [a.get("href", "") for a in soup.find_all("a", href=True)]

        details = set()
        for href in links:
            for pat in source.get("detail_patterns", []):
                if re.search(pat, href):
                    details.add(href)
                    break

        dates = []
        for pat in DATE_PATTERNS:
            dates.extend(pat.findall(text))

        depths = [m.group(0) for m in DEPTH_RE.finditer(text)]
        ranges = [m.group(0) for m in RANGE_RE.finditer(text)]
        aori_hits = {w: text.count(w) for w in AORI_WORDS if w in text}
        neg_hits = {w: text.count(w) for w in NEGATIVE_WORDS if w in text}
        context_hits = {w: text.count(w) for w in CONTEXT_WORDS if w in text}

        item.update({
            "status": "ok",
            "title": title[:180],
            "text_chars": len(text),
            "anchor_count": len(links),
            "detail_link_count": len(details),
            "detail_link_samples": sorted(details)[:8],
            "date_mentions": len(dates),
            "date_samples": dates[:8],
            "aori_hits": aori_hits,
            "negative_hits": neg_hits,
            "depth_mentions": len(depths) + len(ranges),
            "depth_samples": (depths + ranges)[:12],
            "context_hits": context_hits,
            "looks_useful": bool(aori_hits and (dates or details)),
        })
    except Exception as exc:
        item.update({
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "looks_useful": False,
        })
    return item


def main():
    results = []
    with ThreadPoolExecutor(max_workers=min(10, len(SOURCES))) as pool:
        futures = {pool.submit(probe, src): src["name"] for src in SOURCES}
        for future in as_completed(futures):
            results.append(future.result())
    order = {src["name"]: i for i, src in enumerate(SOURCES)}
    results.sort(key=lambda x: order.get(x.get("name"), 999))
    summary = {
        "checked_at": NOW.isoformat(timespec="seconds"),
        "source_count": len(results),
        "ok": sum(x.get("status") == "ok" for x in results),
        "useful": sum(bool(x.get("looks_useful")) for x in results),
        "with_depth": sum(int(x.get("depth_mentions", 0)) > 0 for x in results),
        "with_detail_links": sum(int(x.get("detail_link_count", 0)) > 0 for x in results),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if summary["ok"] == 0:
        raise SystemExit("No candidate source was reachable")


if __name__ == "__main__":
    main()

# v2 structured-signal probe trigger
