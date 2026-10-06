#!/usr/bin/env python3
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
REGIONS = ["越前", "敦賀", "若狭", "小浜", "舞鶴", "丹後"]
QUERY_TEMPLATES = [
    "{region} アオリイカ ティップラン 遊漁船 船長ブログ",
    "{region} アオリイカ ティップラン 水深 ボトム 釣果",
    "{region} アオリイカ 釣果 船 マリーナ ブログ",
]
TARGET_WORDS = ("アオリ", "アオリイカ", "ティップラン", "エギング")
NEGATIVE_WORDS = ("渋い", "厳しい", "釣れない", "釣れず", "反応なし", "ボウズ", "坊主", "チェイス")
DIRECT_WORDS = ("遊漁船", "釣り船", "釣船", "船長", "船宿")
MARINA_WORDS = ("マリーナ", "レンタルボート")
REPORT_WORDS = ("釣果", "釣行", "実釣", "ブログ", "釣果情報")
GENERIC_WORDS = ("初心者", "とは", "仕掛け", "入門", "おすすめタックル")
AGGREGATOR_DOMAINS = {"blogmura.com", "chowari.jp", "egifun.net"}
MULTITENANT_HOSTS = {"ameblo.jp", "plaza.rakuten.co.jp"}
KNOWN_FILE = Path("data/source-registry.json")
OUT_FILE = Path("data/source-candidates.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 16; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141 Mobile Safari/537.36",
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.5",
    "Cache-Control": "no-cache",
}
DATE_PATTERNS = [
    re.compile(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})"),
    re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日"),
]
DEPTH_RE = re.compile(r"(?:水深\s*)?(\d{1,2})(?:\s*[〜~～\-]\s*(\d{1,2}))?\s*(?:m|Ｍ|メートル)", re.I)


def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.mount("https://", HTTPAdapter(max_retries=Retry(
        total=2, connect=2, read=2, backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )))
    return s


def host(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def base_domain(h):
    parts = h.split(".")
    if len(parts) <= 2:
        return h
    if len(parts) >= 3 and parts[-2] in {"co","ne","or","ac","go"} and parts[-1] == "jp":
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def site_key(url):
    p = urlparse(url)
    h = (p.hostname or "").lower()
    path_parts = [x for x in p.path.split("/") if x]
    if h == "ameblo.jp" and path_parts:
        return f"ameblo.jp/{path_parts[0]}"
    if h == "plaza.rakuten.co.jp" and path_parts:
        return f"plaza.rakuten.co.jp/{path_parts[0]}"
    if h.endswith(".seesaa.net") or h.endswith(".hatenablog.com") or h.endswith(".blog.fc2.com"):
        return h
    return base_domain(h)


def known_site_keys():
    if not KNOWN_FILE.exists():
        return set()
    data = json.loads(KNOWN_FILE.read_text(encoding="utf-8"))
    out = set()
    for src in data.get("sources", []):
        url = src.get("url") or ""
        if url:
            out.add(site_key(url))
    return out


def parse_dates(text):
    out = []
    for pat in DATE_PATTERNS:
        for m in pat.finditer(text or ""):
            try:
                d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST).date()
            except ValueError:
                continue
            if d <= NOW.date() + timedelta(days=1):
                out.append(d)
    return sorted(set(out), reverse=True)


def freshness_from_text(text):
    dates = parse_dates(text)
    if not dates:
        return "unknown", None, None
    d = dates[0]
    age = (NOW.date() - d).days
    if age <= 30:
        label = "current_30d"
    elif age <= 90:
        label = "current_90d"
    elif age <= 365:
        label = "recent_year"
    else:
        label = "historical"
    return label, d.isoformat(), age


def classify_source(text, url):
    d = base_domain(host(url))
    t = text or ""
    if d in AGGREGATOR_DOMAINS:
        return "aggregator", False
    h = host(url)
    # Multi-tenant blog hosts are not primary charter sources merely because
    # an article mentions a skipper/boat. Account identity must be verified
    # separately before promotion.
    if h == "ameblo.jp" or h.endswith(".seesaa.net") or h.endswith(".hatenablog.com") or h.endswith(".blog.fc2.com") or h == "plaza.rakuten.co.jp":
        return "blog", False
    if any(w in t for w in DIRECT_WORDS):
        return "charter", True
    if any(w in t for w in MARINA_WORDS):
        return "marina", True
    if any(w in t for w in ("釣具", "フィッシングエイト", "上州屋", "FISHERS")):
        return "tackle_media", False
    return "web_report", False


def score_result(text, url, region):
    score = 0
    reasons = []
    if region in text:
        score += 20; reasons.append("region")
    if "アオリ" in text:
        score += 25; reasons.append("aori")
    if "ティップラン" in text:
        score += 20; reasons.append("tiprun")
    if "エギング" in text:
        score += 8; reasons.append("eging")
    if "水深" in text or DEPTH_RE.search(text):
        score += 12; reasons.append("depth")
    if "釣果" in text:
        score += 8; reasons.append("catch")
    if any(w in text for w in DIRECT_WORDS + MARINA_WORDS):
        score += 15; reasons.append("direct_source")
    if any(w in text for w in REPORT_WORDS):
        score += 6; reasons.append("report")
    freshness, observed, age = freshness_from_text(text)
    if age is not None:
        if age <= 30:
            score += 15; reasons.append("date_30d")
        elif age <= 90:
            score += 10; reasons.append("date_90d")
        elif age > 365:
            score -= 15; reasons.append("old_penalty")
    stype, direct = classify_source(text, url)
    if stype == "aggregator":
        score -= 15; reasons.append("aggregator_penalty")
    if any(w in text for w in GENERIC_WORDS) and not any(w in text for w in ("釣果","釣行","遊漁船","船長")):
        score -= 10; reasons.append("generic_penalty")
    return max(0, min(100, score)), reasons, freshness, observed, age, stype, direct


def yahoo_search(region, query):
    s = make_session()
    url = "https://search.yahoo.co.jp/search?p=" + quote_plus(query)
    r = s.get(url, timeout=(7, 22))
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    rows = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        if href.startswith("//"):
            href = "https:" + href
        if not href.startswith("http"):
            continue
        h = host(href)
        if not h or h.endswith("yahoo.co.jp") or h.endswith("yahoo-net.jp"):
            continue
        text = " ".join(a.stripped_strings)
        if len(text) < 18 or not any(w in text for w in TARGET_WORDS):
            continue
        key = href.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        rows.append({"region": region, "query": query, "url": key, "search_text": text[:700]})
        if len(rows) >= 15:
            break
    return rows


def published_date_from_page(soup):
    raw_values = []
    for meta in soup.find_all("meta"):
        key = (meta.get("property") or meta.get("name") or "").lower()
        if key in ("article:published_time", "datepublished", "date", "pubdate") and meta.get("content"):
            raw_values.append(meta.get("content"))
    for tag in soup.find_all("time"):
        if tag.get("datetime"):
            raw_values.append(tag.get("datetime"))
    dates = []
    for raw in raw_values:
        nums = [int(x) for x in re.findall(r"\d+", raw or "")]
        if len(nums) < 3:
            continue
        try:
            d = datetime(nums[0], nums[1], nums[2], tzinfo=JST).date()
        except ValueError:
            continue
        if d <= NOW.date() + timedelta(days=1):
            dates.append(d)
    return max(dates) if dates else None


def verify_page(candidate):
    s = make_session()
    out = dict(candidate)
    try:
        r = s.get(candidate["url"], timeout=(7, 18), allow_redirects=True)
        out["http_status"] = r.status_code
        out["final_url"] = r.url
        out["bytes"] = len(r.content)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        text = " ".join(soup.stripped_strings)
        page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
        intro = text[:1800]
        identity_words = DIRECT_WORDS + MARINA_WORDS
        ops_words = ("予約", "乗船", "出船", "料金", "お問い合わせ", "電話", "アクセス")
        direct_in_title = any(w in page_title for w in identity_words)
        direct_in_intro = any(w in intro for w in identity_words)
        ops_hits = sum(1 for w in ops_words if w in intro)
        out["page_title"] = page_title[:220]
        # Primary-source status must be visible in the page title itself.
        # Article bodies often mention a skipper/charter they visited, which
        # must not turn a personal/media article into a primary source.
        out["page_direct_identity"] = bool(direct_in_title)
        out["page_target_hits"] = {w: text.count(w) for w in TARGET_WORDS if w in text}
        out["page_region_hit"] = candidate["region"] in text
        pd = published_date_from_page(soup)
        if pd:
            age = (NOW.date() - pd).days
            if age <= 30:
                f = "current_30d"
            elif age <= 90:
                f = "current_90d"
            elif age <= 365:
                f = "recent_year"
            else:
                f = "historical"
            observed = pd.isoformat()
        else:
            f, observed, age = "unknown", None, None
        out["page_freshness"] = f
        out["page_observed_date"] = observed
        out["page_date_age_days"] = age
        depths = []
        for m in DEPTH_RE.finditer(text[:30000]):
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) else None
            if 2 <= lo <= 80 and (hi is None or 2 <= hi <= 80):
                depths.append(m.group(0))
        out["page_depth_samples"] = depths[:8]
        out["page_negative_signals"] = [w for w in NEGATIVE_WORDS if w in text]
        out["verified"] = bool(out["page_target_hits"] and (out["page_region_hit"] or candidate.get("region_explicit")))
    except Exception as exc:
        out["verified"] = False
        out["verify_error"] = f"{type(exc).__name__}: {exc}"[:260]
    return out


def main():
    known = known_site_keys()
    search_rows = []
    diagnostics = []
    tasks = []
    for tmpl in QUERY_TEMPLATES:
        for region in REGIONS:
            q = tmpl.format(region=region)
            tasks.append((region, q))

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(yahoo_search, region, q): (region, q) for region, q in tasks}
        for future in as_completed(futures):
            region, q = futures[future]
            try:
                rows = future.result()
                diagnostics.append({"region": region, "query": q, "status": "ok", "results": len(rows)})
                search_rows.extend(rows)
            except Exception as exc:
                diagnostics.append({"region": region, "query": q, "status": "error", "error": f"{type(exc).__name__}: {exc}"[:240]})

    by_url = {}
    for row in search_rows:
        key = row["url"]
        score, reasons, fresh, observed, age, stype, direct = score_result(row["search_text"], row["url"], row["region"])
        cand = {
            "id": "source-" + hashlib.sha1((site_key(key) + "|" + key).encode("utf-8")).hexdigest()[:16],
            "region": row["region"],
            "url": key,
            "site_key": site_key(key),
            "domain": base_domain(host(key)),
            "host": host(key),
            "search_text": row["search_text"][:600],
            "score": score,
            "reasons": reasons,
            "search_freshness": fresh,
            "search_observed_date": observed,
            "search_date_age_days": age,
            "source_type": stype,
            "direct_source": direct,
            "region_explicit": "region" in reasons,
            "known_source": site_key(key) in known,
        }
        old = by_url.get(key)
        if old is None or cand["score"] > old["score"]:
            by_url[key] = cand

    unknown = [x for x in by_url.values() if not x["known_source"] and x["score"] >= 35]
    unknown.sort(key=lambda x: (-x["score"], x["domain"], x["url"]))

    # Verify the strongest candidates against their actual page. Search
    # snippets are discovery hints, never final evidence.
    to_verify = unknown[:30]
    verified_rows = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(verify_page, x): x["id"] for x in to_verify}
        for future in as_completed(futures):
            verified_rows.append(future.result())

    verified_by_id = {x["id"]: x for x in verified_rows}
    candidates = []
    for x in unknown:
        row = verified_by_id.get(x["id"], x)
        verified = bool(row.get("verified"))
        page_recent = row.get("page_freshness") in ("current_30d", "current_90d")
        search_recent = row.get("search_freshness") in ("current_30d", "current_90d")
        stype = row.get("source_type")
        page_direct = bool(row.get("page_direct_identity"))
        # Tier A = verified primary source identity on the page itself.
        # Mentions of a skipper/charter inside somebody else's article are not
        # enough. Aggregators remain discovery-only.
        if (
            stype != "aggregator"
            and page_direct
            and verified
            and row["score"] >= 55
            and row.get("region_explicit")
        ):
            tier = "A"
        elif (
            stype != "aggregator"
            and not page_direct
            and verified
            and row["score"] >= 55
            and row.get("region_explicit")
            and (search_recent or page_recent)
        ):
            tier = "B"
        else:
            tier = "C"
        row["tier"] = tier
        row["status"] = "candidate"
        row["auto_promote"] = False
        candidates.append(row)

    # One source candidate per site/account. Keep the strongest page and
    # preserve other discovered URLs for later adapter building.
    tier_rank = {"A": 0, "B": 1, "C": 2}
    by_site = {}
    for row in candidates:
        key = row["site_key"]
        old = by_site.get(key)
        if old is None:
            row["regions"] = [row["region"]]
            row["alternate_urls"] = []
            by_site[key] = row
            continue
        old["regions"] = sorted(set(old.get("regions", [old["region"]]) + [row["region"]]))
        if row["url"] != old["url"] and row["url"] not in old["alternate_urls"]:
            old["alternate_urls"].append(row["url"])
        better = (tier_rank.get(row["tier"], 9), -row["score"]) < (tier_rank.get(old["tier"], 9), -old["score"])
        if better:
            row["regions"] = old["regions"]
            row["alternate_urls"] = sorted(set(old["alternate_urls"] + [old["url"]]))
            by_site[key] = row
    candidates = list(by_site.values())
    candidates.sort(key=lambda x: (tier_rank.get(x["tier"],9), -x["score"], x["site_key"]))
    payload = {
        "updated_at": NOW.isoformat(timespec="seconds"),
        "engine": "Yahoo Japan HTML",
        "policy": "Keyword discovery only. Search snippets never enter catch scoring. Candidate pages are re-fetched; A/B are review candidates, C is retained only for audit. No candidate is auto-promoted.",
        "query_count": len(tasks),
        "query_ok": sum(x["status"] == "ok" for x in diagnostics),
        "query_error": sum(x["status"] == "error" for x in diagnostics),
        "candidate_count": len(candidates),
        "tier_counts": {t: sum(x["tier"] == t for x in candidates) for t in ("A","B","C")},
        "diagnostics": sorted(diagnostics, key=lambda x: (x["region"], x["query"])),
        "candidates": candidates[:100],
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "query_count": payload["query_count"],
        "query_ok": payload["query_ok"],
        "query_error": payload["query_error"],
        "candidate_count": payload["candidate_count"],
        "tier_counts": payload["tier_counts"],
        "verified": sum(bool(x.get("verified")) for x in candidates),
        "with_depth_page": sum(bool(x.get("page_depth_samples")) for x in candidates),
        "top_A": [
            {"region":x["region"],"domain":x["domain"],"score":x["score"],"url":x["url"]}
            for x in candidates if x["tier"] == "A"
        ][:12],
    }, ensure_ascii=False, indent=2))

    if payload["query_ok"] < 12:
        raise SystemExit("too many keyword search failures")
    if not candidates:
        raise SystemExit("no keyword candidates")


if __name__ == "__main__":
    main()
