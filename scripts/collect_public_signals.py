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
        "name": "春定丸",
        "kind": "charter",
        "url": "https://ameblo.jp/synteimaru/",
        "default_area": "敦賀",
        "detail_patterns": [r"/synteimaru/entry-\d+\.html"],
        "detail_limit": 12,
    },
    {
        "name": "天徳丸",
        "kind": "charter",
        "url": "https://tentokumaru.com/fishing_blog/",
        "default_area": "越前",
    },
    {
        "name": "瑞祥丸",
        "kind": "charter",
        "url": "https://zuishomaru.com/category/fishing/",
        "default_area": "敦賀",
        "default_aori_method": "ティップラン",
    },
    {
        "name": "若狭マリンプラザ",
        "kind": "marina",
        "url": "https://www.marineplaza-marina.com/?cat=11",
        "default_area": "若狭",
        "detail_patterns": [r"[?&]p=\d+"],
        "detail_limit": 12,
    },
    {
        "name": "まるまる丸",
        "kind": "charter",
        "url": "https://marumarumaru.co.jp/report/",
        "default_area": "敦賀",
    },
    {
        "name": "心友丸",
        "kind": "charter",
        "url": "https://www.shinyuumaru.com/contents/information.php",
        "default_area": "越前",
    },
    {
        "name": "MIYAMOTOMARU2",
        "kind": "charter",
        "url": "https://ameblo.jp/miyamotomar/",
        "default_area": "舞鶴",
        "detail_patterns": [r"/miyamotomar/entry-\d+\.html"],
        "detail_limit": 12,
    },
    {
        "name": "小浜マリーナ",
        "kind": "marina",
        "url": "https://www.obama-marina.com/catch/index.php",
        "default_area": "若狭",
    },
    {
        "name": "福丸",
        "kind": "charter",
        "url": "https://www.e-fukumaru.com/",
        "default_area": "若狭",
        "detail_patterns": [r"/news/\d+"],
        "detail_limit": 10,
    },
    {
        "name": "SUPER VIKING",
        "kind": "charter_aggregator",
        "url": "https://reserve.castingnet.jp/ship00107c.html",
        "default_area": "若狭",
    },
    {
        "name": "あみや渡船",
        "kind": "raft",
        "url": "https://www.fishing-v.jp/choka/choka_detail.php?s=582",
        "default_area": "若狭",
    },
    {
        "name": "ヴィーナス",
        "kind": "charter",
        "url": "https://www.fisher-venus.com/chouka/",
        "default_area": "丹後",
        "detail_patterns": [r"/chouka/.+"],
        "detail_limit": 12,
    },
    {
        "name": "オールブルー",
        "kind": "charter",
        "url": "https://www.allbluemarine.com/",
        "default_area": "丹後",
    },
    {
        "name": "ちどり丸",
        "kind": "charter_aggregator",
        "url": "https://www.fishing-v.jp/choka/choka_detail.php?s=1748",
        "default_area": "丹後",
    },
    {
        "name": "上州屋 新敦賀店",
        "kind": "tackle_shop",
        "url": "https://www.johshuya.co.jp/shop/choka.php?s=151",
        "default_area": "敦賀",
    },
    {
        "name": "泰丸",
        "kind": "charter",
        "url": "https://www.taimaru.jp/fishingpost/",
        "default_area": "敦賀",
        "default_aori_method": "ティップラン",
        "detail_patterns": [r"/fishingpost/\d+/"],
        "detail_limit": 12,
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
        "detail_patterns": [r"/fishing/\d+"],
        "detail_limit": 10,
    },
    {
        "name": "TRITON",
        "kind": "charter",
        "url": "https://triton-maizuru.com/topics.html",
        "default_area": "舞鶴",
        "detail_patterns": [r"/blog/\d+\.html"],
        "detail_limit": 12,
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
        "detail_patterns": [r"/blog_articles/\d+\.html"],
        "detail_limit": 12,
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
TRIP_MD_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})日?(?:の)?釣行")
COUNT_RE = re.compile(r"(?<!\d)(\d{1,3})\s*(?:杯|ハイ)")
DEPTH_RE = re.compile(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*(?:m|メートル)", re.I)
DEPTH_RANGE_RE = re.compile(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*(?:m)?\s*[~\-]\s*(\d{1,2}(?:\.\d+)?)\s*(?:m|メートル)", re.I)
WATER_RANGE_RE = re.compile(r"水深\s*(\d{1,2}(?:\.\d+)?)\s*(?:m)?\s*[~\-]\s*(\d{1,2}(?:\.\d+)?)\s*(?:m|メートル)", re.I)
WATER_SINGLE_RE = re.compile(r"水深\s*(\d{1,2}(?:\.\d+)?)\s*(?:m|メートル)", re.I)
BOTTOM_OFFSET_RE = re.compile(r"(?:ボトム|底)(?:から|より)?\s*(\d{1,2}(?:\.\d+)?)\s*(?:m|メートル)", re.I)
TANA_RANGE_RE = re.compile(r"(?:棚|タナ)\s*(?:は|が|:|：)?\s*(\d{1,2}(?:\.\d+)?)\s*(?:m)?\s*[~\-]\s*(\d{1,2}(?:\.\d+)?)\s*(?:m|メートル)", re.I)
TANA_SINGLE_RE = re.compile(r"(?:棚|タナ)\s*(?:は|が|:|：)?\s*(\d{1,2}(?:\.\d+)?)\s*(?:m|メートル)", re.I)
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


def detect_evidence_role(text):
    t = normalize(text)
    strong_catch_markers = (
        "ヒット", "キャッチ", "釣れた", "釣れました", "釣れて", "釣れ", "竿頭",
        "トップ", "船中", "全員安打", "連発", "乗って", "乗りました", "抱いた",
    )
    weak_catch_markers = (
        "釣果", "乗り", "アタリ", "あたり", "反応", "チェイス", "見えイカ",
        "ボウズ", "坊主", "渋い", "厳しい",
    )
    schedule_markers = (
        "募集中", "募集", "予約受付", "ご予約", "空き", "残り", "満席",
        "出船予定", "料金", "レンタル", "受付時間", "プラン",
    )

    if any(w in t for w in strong_catch_markers):
        return "catch"

    catch_score = sum(1 for w in weak_catch_markers if w in t)
    if COUNT_RE.search(t):
        catch_score += 2
    if any(w in t for w in NEGATIVE_WORDS):
        catch_score += 1
    schedule_score = sum(1 for w in schedule_markers if w in t)

    if catch_score >= 2:
        return "catch"
    if schedule_score >= 1 and catch_score == 0:
        return "schedule"
    return "info"


def detect_time_mode(text):
    t = normalize(text)
    day_hits = any(w in t for w in ("Dayティップラン", "DAYティップラン", "デイティップラン", "昼ティップラン", "昼便", "午前便", "午後便"))
    night_hits = any(w in t for w in ("ナイトティップラン", "Nightティップラン", "NIGHTティップラン", "夜ティップラン", "ナイト便", "夜便", "半夜便", "深夜便"))
    if day_hits and night_hits:
        return "mixed"
    if day_hits:
        return "day"
    if night_hits:
        return "night"
    return "unknown"


def classify_type(text, kind):
    if kind == "marina":
        return "boat", "マイボート"
    if kind == "raft" or "筏" in text:
        return "raft", "筏エギング" if ("エギ" in text or "アオリ" in text) else "筏"
    if "ティップラン" in text:
        return "boat", "ティップラン"
    if kind in ("charter", "charter_aggregator") or any(w in text for w in BOAT_WORDS):
        return "boat", "船"
    if any(w in text for w in SHORE_WORDS):
        return "shore", "エギング" if "エギング" in text else "ショア"
    return "unknown", "unknown"


def extract_depths(segment):
    text = normalize(segment)
    water = []
    bottom_offsets = []
    tana = []
    contexts = []
    target_words = ("アオリ", "アオリイカ", "ティップラン")
    competing_words = (
        "キジハタ", "アコウ", "カサゴ", "キス", "マイカ", "シロイカ",
        "ケンサキ", "コウイカ", "サゴシ", "サワラ", "マダイ", "アジ",
        "サバ", "カマス", "青物",
    )
    sentence_breaks = "。！？!?"

    def sentence_bounds(start, end):
        left = start
        while left > 0 and text[left - 1] not in sentence_breaks:
            left -= 1
        right = end
        while right < len(text) and text[right] not in sentence_breaks:
            right += 1
        return left, right

    def relation_context(start, end):
        left, right = sentence_bounds(start, end)
        sentence = text[left:right]
        same_target = [w for w in target_words if w in sentence]
        same_competing = [w for w in competing_words if w in sentence]
        if same_target and not (same_competing and "アオリ" not in sentence):
            return sentence, same_target, "A"
        if same_competing:
            return None

        # Some boat reports put "night tip-run" and the water depth in
        # consecutive short clauses without punctuation. Use proximity as B,
        # but reject when another species is closer to the number.
        win_left = max(0, start - 180)
        win_right = min(len(text), end + 120)
        window = text[win_left:win_right]
        near_left = max(0, start - 80)
        near_right = min(len(text), end + 80)
        near = text[near_left:near_right]
        if any(w in near for w in competing_words) and "アオリ" not in near:
            return None
        targets = [w for w in target_words if w in window]
        if targets:
            return window, targets, "B"
        return None

    def append_context(kind, value, match, relation):
        evidence, keywords, grade = relation
        contexts.append({
            "kind": kind,
            "value_m": value,
            "keywords": keywords[:6],
            "confidence": grade,
            "evidence": evidence[:320],
        })

    # Explicit seabed/water depth: only phrases that actually say 水深.
    for m in WATER_RANGE_RE.finditer(text):
        lo, hi = float(m.group(1)), float(m.group(2))
        if not (2 <= lo <= 80 and 2 <= hi <= 80):
            continue
        relation = relation_context(m.start(), m.end())
        if not relation:
            continue
        vals = [round(min(lo, hi), 1), round(max(lo, hi), 1)]
        water.extend(vals)
        append_context("water_depth_range", vals, m, relation)

    for m in WATER_SINGLE_RE.finditer(text):
        value = float(m.group(1))
        if not (2 <= value <= 80):
            continue
        relation = relation_context(m.start(), m.end())
        if not relation:
            continue
        value = round(value, 1)
        water.append(value)
        append_context("water_depth", value, m, relation)

    # "bottom +5m" means strike layer above the seabed, not 5m water depth.
    for m in BOTTOM_OFFSET_RE.finditer(text):
        value = float(m.group(1))
        if not (0 < value <= 30):
            continue
        relation = relation_context(m.start(), m.end())
        if not relation:
            continue
        value = round(value, 1)
        bottom_offsets.append(value)
        append_context("bottom_offset", value, m, relation)

    # 棚/タナ is kept separately because it can be a layer measured from surface.
    for m in TANA_RANGE_RE.finditer(text):
        lo, hi = float(m.group(1)), float(m.group(2))
        if not (0 < lo <= 80 and 0 < hi <= 80):
            continue
        relation = relation_context(m.start(), m.end())
        if not relation:
            continue
        vals = [round(min(lo, hi), 1), round(max(lo, hi), 1)]
        tana.extend(vals)
        append_context("tana_range", vals, m, relation)

    for m in TANA_SINGLE_RE.finditer(text):
        value = float(m.group(1))
        if not (0 < value <= 80):
            continue
        relation = relation_context(m.start(), m.end())
        if not relation:
            continue
        value = round(value, 1)
        tana.append(value)
        append_context("tana", value, m, relation)

    return sorted(set(water)), sorted(set(bottom_offsets)), sorted(set(tana)), contexts[:10]

def discover_detail_links(source, soup):
    patterns = source.get("detail_patterns") or []
    if not patterns:
        return []
    base = source["url"]
    seen = set()
    out = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not any(re.search(p, href) for p in patterns):
            continue
        url = urljoin(base, href)
        if url.rstrip("/") == base.rstrip("/") or url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= int(source.get("detail_limit", 10)):
            break
    return out


def published_date_from_soup(soup, text):
    candidates = []
    for meta in soup.find_all("meta"):
        key = (meta.get("property") or meta.get("name") or "").lower()
        if key in ("article:published_time", "datepublished", "date") and meta.get("content"):
            candidates.append(meta.get("content"))
    for time_tag in soup.find_all("time"):
        if time_tag.get("datetime"):
            candidates.append(time_tag.get("datetime"))
    for raw in candidates:
        nums = [int(x) for x in re.findall(r"\d+", raw or "")]
        if len(nums) >= 3:
            try:
                d = datetime(nums[0], nums[1], nums[2], tzinfo=JST)
            except ValueError:
                continue
            age = (NOW.date() - d.date()).days
            if 0 <= age <= WINDOW_DAYS:
                return d.date().isoformat()
    for m in DATE_RE.finditer(normalize(text)):
        d = parse_date(m.group(0))
        if d:
            return d
    return None


def split_detail_segments(text, page_date):
    normalized = normalize(text)
    matches = list(TRIP_MD_RE.finditer(normalized))
    if matches and page_date:
        year = int(page_date[:4])
        out = []
        for i, m in enumerate(matches):
            month, day = int(m.group(1)), int(m.group(2))
            try:
                d = datetime(year, month, day, tzinfo=JST)
            except ValueError:
                continue
            age = (NOW.date() - d.date()).days
            if not (0 <= age <= WINDOW_DAYS):
                continue
            end = matches[i + 1].start() if i + 1 < len(matches) else min(len(normalized), m.start() + 2600)
            out.append((d.date().isoformat(), normalized[m.start():end]))
        if out:
            return out
    if page_date:
        return [(page_date, normalized[:5000])]
    return split_recent_segments(normalized)


def fetch_detail_signals(source, detail_urls, sess):
    signals = []
    errors = 0
    fetched = 0
    for url in detail_urls:
        try:
            r = sess.get(url, timeout=(6, 18), allow_redirects=True)
            r.raise_for_status()
            fetched += 1
            soup = BeautifulSoup(r.content, "html.parser")
            text = soup.get_text(" ", strip=True)
            page_date = published_date_from_soup(soup, text)
            title = clean(soup.title.get_text(" ", strip=True) if soup.title else "")
            # In detail articles, trip-date paragraphs often omit the species/method
            # because the title already says "アオリイカ ティップラン".
            inherited_context = title if any(w in title for w in AORI_WORDS) else ""
            detail_source = dict(source)
            detail_source["url"] = r.url
            for date, segment in split_detail_segments(text, page_date):
                sig = signal_from_segment(detail_source, date, segment, inherited_context=inherited_context)
                if sig:
                    sig["detail_url"] = r.url
                    sig["evidence_scope"] = "detail"
                    signals.append(sig)
        except Exception:
            errors += 1
    return signals, fetched, errors


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


def signal_from_segment(source, date, segment, inherited_context=""):
    analysis_text = normalize((inherited_context + " " + segment).strip())
    if not any(w in analysis_text for w in AORI_WORDS):
        return None

    area = detect_area(analysis_text, source.get("default_area"))
    typ, method = classify_type(analysis_text, source["kind"])
    if typ == "boat" and method == "船" and source.get("default_aori_method") and "アオリ" in analysis_text:
        method = source["default_aori_method"]
    segment_mode = detect_time_mode(segment)
    inherited_mode = detect_time_mode(inherited_context)
    if segment_mode == "unknown":
        time_mode = inherited_mode
    elif segment_mode == "mixed" and inherited_mode in ("day", "night"):
        time_mode = inherited_mode
    else:
        time_mode = segment_mode
    evidence_role = detect_evidence_role(analysis_text)
    depths, bottom_offsets, tana_depths, depth_contexts = extract_depths(analysis_text)
    negatives = [w for w in NEGATIVE_WORDS if w in analysis_text]
    bait = [w for w in BAIT_WORDS if w in analysis_text]
    counts = sorted({int(x) for x in COUNT_RE.findall(analysis_text) if 0 < int(x) <= 200})

    quality = 25
    quality += 20 if area else 0
    quality += 15 if typ != "unknown" else 0
    quality += 15 if "アオリ" in analysis_text else 8
    quality += 15 if (depths or bottom_offsets or tana_depths) else 0
    quality += 5 if negatives else 0
    # Numeric "X杯" mentions can mix skipper total, top angler and separate
    # time blocks. Keep them as evidence, but do not boost confidence until a
    # source-specific parser confirms their semantic role.
    quality = min(100, quality)
    confidence = "A" if quality >= 75 else ("B" if quality >= 55 else "C")

    depth_confidence = "none"
    if depths or bottom_offsets or tana_depths:
        depth_confidence = "A" if any(x.get("confidence") == "A" for x in depth_contexts) else "B"

    stable = "|".join([
        source["name"], date, area or "unknown", typ, method, time_mode,
        ",".join(str(x) for x in depths),
        ",".join(str(x) for x in bottom_offsets),
        ",".join(str(x) for x in tana_depths),
        ",".join(str(x) for x in counts),
    ])
    sid = "signal-" + hashlib.sha1(stable.encode("utf-8")).hexdigest()[:16]

    usable_for_decision = bool(
        confidence in ("A", "B")
        and evidence_role == "catch"
        and area
        and typ in ("shore", "boat", "raft")
    )

    return {
        "id": sid,
        "date": date,
        "area": area,
        "type": typ,
        "method": method,
        "time_mode": time_mode,
        "evidence_role": evidence_role,
        "source": source["name"],
        "source_kind": source["kind"],
        "url": source["url"],
        "confidence": confidence,
        "quality_score": quality,
        "usable_for_decision": usable_for_decision,
        "depth_m": depths,
        "bottom_offset_m": bottom_offsets,
        "tana_m": tana_depths,
        "depth_confidence": depth_confidence,
        "depth_evidence": depth_contexts,
        "count_mentions": counts,
        "count_confidence": "mention_only" if counts else "none",
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
                sig["evidence_scope"] = "listing"
                signals.append(sig)

        detail_urls = discover_detail_links(source, soup)
        detail_signals, detail_fetched, detail_errors = fetch_detail_signals(source, detail_urls, s)
        signals.extend(detail_signals)
        health.update({
            "status": "ok",
            "recent_segments": len(segments),
            "detail_discovered": len(detail_urls),
            "detail_fetched": detail_fetched,
            "detail_errors": detail_errors,
            "detail_signals": len(detail_signals),
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

    # Compress listing/detail duplicates from the same source-day. If explicit
    # day/night evidence exists, discard unknown/mixed variants from that same
    # source-day-method while preserving separate day and night sessions.
    base_groups = {}
    for sig in all_signals:
        base = "|".join([
            sig.get("source") or "", sig.get("date") or "", sig.get("area") or "",
            sig.get("type") or "", sig.get("method") or "",
        ])
        base_groups.setdefault(base, []).append(sig)

    normalized_signals = []
    for group in base_groups.values():
        explicit_modes = {x.get("time_mode") for x in group if x.get("time_mode") in ("day", "night")}
        if explicit_modes:
            group = [x for x in group if x.get("time_mode") in explicit_modes]
        normalized_signals.extend(group)

    by_session = {}
    for sig in normalized_signals:
        key = "|".join([
            sig.get("source") or "", sig.get("date") or "", sig.get("area") or "",
            sig.get("type") or "", sig.get("method") or "", sig.get("time_mode") or "",
        ])
        old = by_session.get(key)
        richness = (
            int(bool(sig.get("depth_m") or sig.get("bottom_offset_m") or sig.get("tana_m"))) * 100
            + int(sig.get("quality_score", 0))
            + int(sig.get("evidence_scope") == "detail") * 10
        )
        old_richness = -1
        if old:
            old_richness = (
                int(bool(old.get("depth_m") or old.get("bottom_offset_m") or old.get("tana_m"))) * 100
                + int(old.get("quality_score", 0))
                + int(old.get("evidence_scope") == "detail") * 10
            )
        if old is None or richness > old_richness:
            by_session[key] = sig
    signals = sorted(by_session.values(), key=lambda x: (x["date"], x.get("quality_score", 0)), reverse=True)

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
        "trusted_signals": sum(bool(x.get("usable_for_decision")) for x in signals),
        "review_candidates": sum(not bool(x.get("usable_for_decision")) for x in signals),
        "catch_signals": sum(x.get("evidence_role") == "catch" for x in signals),
        "schedule_info": sum(x.get("evidence_role") == "schedule" for x in signals),
        "grade_A": sum(x.get("confidence") == "A" for x in signals),
        "with_depth": sum(bool(x.get("depth_m") or x.get("bottom_offset_m") or x.get("tana_m")) for x in signals),
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
