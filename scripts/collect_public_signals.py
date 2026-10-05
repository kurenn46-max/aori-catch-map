#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
WINDOW_DAYS = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 16; Mobile) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
}

SOURCES = [
    {
        "name": "上州屋 新敦賀店",
        "kind": "tackle_shop",
        "url": "https://www.johshuya.co.jp/shop/choka.php?s=151",
        "default_area": "敦賀",
    },
    {
        "name": "FISHERS",
        "kind": "tackle_shop",
        "url": "https://www.fishers.co.jp/",
        "default_area": None,
    },
    {
        "name": "ブンブン釣行記",
        "kind": "tackle_shop_media",
        "url": "https://bunbun-fishing.com/fishing/",
        "default_area": None,
    },
    {
        "name": "TRITON",
        "kind": "charter",
        "url": "https://triton-maizuru.com/topics.html",
        "default_area": "舞鶴",
    },
    {
        "name": "すばる",
        "kind": "charter",
        "url": "https://subarutango.jimdofree.com/",
        "default_area": "丹後",
    },
    {
        "name": "OCEANS",
        "kind": "charter",
        "url": "https://oceans2009.com/tyoka",
        "default_area": "丹後",
    },
    {
        "name": "シーマン",
        "kind": "charter",
        "url": "https://seaman-tango.com/blog_articles/",
        "default_area": "丹後",
    },
]

AREA_WORDS = {
    "越前": ("越前", "越前海岸", "越前岬", "甲楽城"),
    "敦賀": ("敦賀", "敦賀湾", "敦賀半島", "新敦賀"),
    "若狭": ("若狭", "小浜", "常神", "神子", "犬熊", "田烏", "世久見", "高浜", "音海", "日引"),
    "舞鶴": ("舞鶴", "白杉", "野原", "小橋", "舞鶴湾"),
    "丹後": ("丹後", "京丹後", "網野", "間人", "宮津", "伊根"),
}
AORI_WORDS = ("アオリイカ", "アオリ", "ティップラン", "エギング")
NEGATIVE_WORDS = ("ボウズ", "坊主", "釣れない", "釣れず", "反応なし", "渋い", "厳しい", "チェイス", "見えイカ")
BAIT_WORDS = ("豆アジ", "小アジ", "アジ", "カタクチイワシ", "マイワシ", "ウルメイワシ", "サヨリ", "キビナゴ", "小サバ", "ベイト")
BOAT_WORDS = ("ティップラン", "遊漁船", "船中", "出船", "ボート")
SHORE_WORDS = ("ショア", "陸っぱり", "漁港", "堤防", "防波堤", "磯", "エギング")

FW_TRANS = str.maketrans("０１２３４５６７８９．～〜Ｍｍ", "0123456789.~~Mm")
DATE_RE = re.compile(r"20\d{2}(?:年\s*\d{1,2}月\s*\d{1,2}日|[./-]\d{1,2}[./-]\d{1,2})")
COUNT_RE = re.compile(r"(?<!\d)(\d{1,3})\s*(?:杯|ハイ)")
DEPTH_RE = re.compile(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*(?:m|メートル)", re.I)
DEPTH_RANGE_RE = re.compile(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*(?:m)?\s*[~\-]\s*(\d{1,2}(?:\.\d+)?)\s*(?:m|メートル)", re.I)
DEPTH_CONTEXT_WORDS = ("水深", "ティップラン", "ボトム", "中層", "表層", "レンジ", "タナ", "浅場", "深場", "流し", "ポイント")


def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.mount(
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
    return s


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def normalize(text):
    return clean((text or "").translate(FW_TRANS))


def parse_date(raw):
    s = normalize(raw)
    nums = [int(x) for x in re.findall(r"\d+", s)]
    if len(nums) < 3:
        return None
    try:
        d = datetime(nums[0], nums[1], nums[2], tzinfo=JST)
    except ValueError:
        return None
    age = (NOW.date() - d.date()).days
    if 0 <= age <= WINDOW_DAYS:
        return d.date().isoformat()
    return None


def detect_area(text, default=None):
    hits = []
    for area, words in AREA_WORDS.items():
        score = sum(text.count(w) for w in words)
        if score:
            hits.append((score, area))
    if hits:
        hits.sort(reverse=True)
        return hits[0][1]
    return default


def classify_type(text, kind):
    if "ティップラン" in text:
        return "boat", "ティップラン"
    if kind == "charter" or any(w in text for w in BOAT_WORDS):
        return "boat", "船"
    if any(w in text for w in SHORE_WORDS):
        return "shore", "エギング" if "エギング" in text else "ショア"
    return "unknown", "unknown"


def extract_depths(segment):
    text = normalize(segment)
    found = []
    contexts = []

    def add_depth(value, start, end):
        if not (2 <= value <= 80):
            return
        left = max(0, start - 70)
        right = min(len(text), end + 70)
        ctx = text[left:right]
        nearby = [w for w in DEPTH_CONTEXT_WORDS if w in ctx]
        if not nearby:
            return
        found.append(round(value, 1))
        contexts.append({"depth_m": round(value, 1), "keywords": nearby[:5]})

    for m in DEPTH_RANGE_RE.finditer(text):
        lo, hi = float(m.group(1)), float(m.group(2))
        if 2 <= lo <= 80 and 2 <= hi <= 80:
            ctx = text[max(0, m.start() - 70):min(len(text), m.end() + 70)]
            nearby = [w for w in DEPTH_CONTEXT_WORDS if w in ctx]
            if nearby:
                found.extend([round(lo, 1), round(hi, 1)])
                contexts.append({"range_m": [round(min(lo, hi), 1), round(max(lo, hi), 1)], "keywords": nearby[:5]})

    for m in DEPTH_RE.finditer(text):
        add_depth(float(m.group(1)), m.start(), m.end())

    unique = sorted(set(found))
    return unique, contexts[:8]


def split_recent_segments(text):
    normalized = normalize(text)
    matches = list(DATE_RE.finditer(normalized))
    out = []
    for i, m in enumerate(matches):
        date = parse_date(m.group(0))
        if not date:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(normalized), m.start() + 3500)
        segment = normalized[m.start():end]
        if len(segment) > 3500:
            segment = segment[:3500]
        out.append((date, segment))
    return out


def signal_from_segment(source, date, segment):
    if not any(w in segment for w in AORI_WORDS):
        return None

    area = detect_area(segment, source.get("default_area"))
    typ, method = classify_type(segment, source["kind"])
    depths, depth_contexts = extract_depths(segment)
    negatives = [w for w in NEGATIVE_WORDS if w in segment]
    bait = [w for w in BAIT_WORDS if w in segment]
    counts = sorted({int(x) for x in COUNT_RE.findall(segment) if 0 < int(x) <= 200})

    quality = 25
    quality += 20 if area else 0
    quality += 15 if typ != "unknown" else 0
    quality += 15 if "アオリ" in segment else 8
    quality += 15 if depths else 0
    quality += 5 if negatives else 0
    quality += 5 if counts else 0
    quality = min(100, quality)
    confidence = "A" if quality >= 75 else ("B" if quality >= 55 else "C")

    depth_confidence = "none"
    if depths:
        strong = any("水深" in x.get("keywords", []) or "ティップラン" in x.get("keywords", []) for x in depth_contexts)
        depth_confidence = "A" if strong else "B"

    stable = "|".join([
        source["name"], date, area or "unknown", typ, method,
        ",".join(str(x) for x in depths),
        ",".join(str(x) for x in counts),
    ])
    sid = "signal-" + hashlib.sha1(stable.encode("utf-8")).hexdigest()[:16]

    return {
        "id": sid,
        "date": date,
        "area": area,
        "type": typ,
        "method": method,
        "source": source["name"],
        "source_kind": source["kind"],
        "url": source["url"],
        "confidence": confidence,
        "quality_score": quality,
        "depth_m": depths,
        "depth_confidence": depth_confidence,
        "depth_evidence": depth_contexts,
        "count_mentions": counts,
        "negative_signals": negatives,
        "bait_signals": bait,
    }


def collect_one(source):
    s = session()
    checked_at = NOW.isoformat(timespec="seconds")
    health = {
        "source": source["name"],
        "url": source["url"],
        "checked_at": checked_at,
    }
    try:
        r = s.get(source["url"], timeout=(6, 18), allow_redirects=True)
        health["http_status"] = r.status_code
        health["bytes"] = len(r.content)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        text = soup.get_text(" ", strip=True)
        segments = split_recent_segments(text)
        signals = []
        for date, segment in segments:
            sig = signal_from_segment(source, date, segment)
            if sig:
                signals.append(sig)
        health.update({
            "status": "ok",
            "recent_segments": len(segments),
            "accepted_signals": len(signals),
        })
        return signals, health
    except Exception as exc:
        health.update({
            "status": "error",
            "recent_segments": 0,
            "accepted_signals": 0,
            "error": f"{type(exc).__name__}: {exc}"[:260],
        })
        return [], health


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/discovery-signals.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    all_signals = []
    health = []
    with ThreadPoolExecutor(max_workers=min(8, len(SOURCES))) as pool:
        futures = {pool.submit(collect_one, src): src["name"] for src in SOURCES}
        for future in as_completed(futures):
            signals, status = future.result()
            all_signals.extend(signals)
            health.append(status)

    order = {src["name"]: i for i, src in enumerate(SOURCES)}
    health.sort(key=lambda x: order.get(x.get("source"), 999))

    by_id = {}
    for sig in all_signals:
        old = by_id.get(sig["id"])
        if old is None or sig["quality_score"] > old["quality_score"]:
            by_id[sig["id"]] = sig
    signals = sorted(by_id.values(), key=lambda x: (x["date"], x.get("quality_score", 0)), reverse=True)

    payload = {
        "updated_at": NOW.isoformat(timespec="seconds"),
        "window_days": WINDOW_DAYS,
        "note": (
            "GitHub Runnerから直接取得できる複数公開情報源を横断。"
            "日付・海域・岸/船・ティップラン・水深文脈・杯数・負情報・ベイト語を抽出し、"
            "水深は周辺文脈が確認できたものだけ採用する。これは発見/補助信号であり、"
            "岸釣果DBへは自動で杯数換算しない。"
        ),
        "source_health": health,
        "signals": signals,
    }

    print(json.dumps({
        "sources_ok": sum(x.get("status") == "ok" for x in health),
        "sources_total": len(health),
        "signals": len(signals),
        "grade_A": sum(x.get("confidence") == "A" for x in signals),
        "with_depth": sum(bool(x.get("depth_m")) for x in signals),
        "boat": sum(x.get("type") == "boat" for x in signals),
        "shore": sum(x.get("type") == "shore" for x in signals),
        "by_source": {h["source"]: h.get("accepted_signals", 0) for h in health},
    }, ensure_ascii=False, indent=2))

    if not args.dry_run:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
