#!/usr/bin/env python3
"""V4.1 verified report discovery lane.

Search is only discovery. A result never becomes evidence until its actual page
is fetched and the article itself contains:
- Aori squid context
- one of the target Sea-of-Japan areas
- a recent date
- catch/negative evidence
- a shore/boat classification

Search-derived evidence is capped at confidence B. It supplements, never
overrides, direct/known-source evidence.
"""
import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from collect_public_signals import (
    NOW, AORI_WORDS, detect_area, extract_primary_detail_text,
    published_date_from_soup, session, signal_from_segment,
    split_detail_segments,
)
from discover_sources import yahoo_search

REGIONS = ["越前", "敦賀", "若狭", "舞鶴", "丹後"]
QUERY_TEMPLATES = [
    "{region} アオリイカ エギング 釣果 {year}",
    "{region} アオリイカ 釣行 釣果 {year}",
    "{region} アオリイカ ティップラン 釣果 水深 {year}",
]
BLOCKED_DOMAINS = {
    "facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com",
    "youtu.be", "tiktok.com", "pinterest.com", "amazon.co.jp",
    "search.yahoo.co.jp", "google.com", "bing.com",
}
AGGREGATOR_DOMAINS = {
    "blogmura.com", "chowari.jp",
}
SOURCE_NAMES = {
    "yamaria.com": "エギCOM",
    "johshuya.co.jp": "上州屋",
    "ishiguro-gr.com": "釣具のイシグロ",
    "bunbun-fishing.com": "ブンブン釣行記",
    "fishers.co.jp": "FISHERS",
    "fishingmax.co.jp": "フィッシングマックス",
    "sumizoku.com": "墨族",
    "anglers.co.jp": "ANGLERS",
    "fishing.ne.jp": "カンパリ",
    "tsurinews.jp": "TSURINEWS",
}
MAX_FETCH = 60


def hostname(url):
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def base_domain(url):
    h = hostname(url)
    bits = h.split(".")
    if len(bits) >= 3 and bits[-2] in {"co", "ne", "or", "go", "ac"} and bits[-1] == "jp":
        return ".".join(bits[-3:])
    return ".".join(bits[-2:]) if len(bits) >= 2 else h


def source_name(url):
    d = base_domain(url)
    return SOURCE_NAMES.get(d, d or "公開Web")


def candidate_score(row):
    txt = row.get("search_text") or ""
    score = 0
    score += 30 if "アオリ" in txt else 0
    score += 15 if "エギング" in txt else 0
    score += 10 if "釣果" in txt or "釣行" in txt else 0
    score += 15 if row.get("region") and row["region"] in txt else 0
    score += 5 if re.search(r"20\d{2}", txt) else 0
    return score


def verify(row):
    url = row["url"]
    domain = base_domain(url)
    if not domain or domain in BLOCKED_DOMAINS or domain in AGGREGATOR_DOMAINS:
        return [], {"url": url, "status": "skipped_domain", "domain": domain}

    sess = session()
    try:
        r = sess.get(url, timeout=(6, 18), allow_redirects=True)
        r.raise_for_status()
        final_url = r.url
        soup = BeautifulSoup(r.content, "html.parser")
        src = {
            "name": source_name(final_url),
            "kind": "web_report",
            "url": final_url,
            "default_area": None,
            "detail_text_limit": 8000,
        }
        text = extract_primary_detail_text(soup, src)
        if not any(w in text for w in AORI_WORDS):
            return [], {"url": final_url, "status": "no_aori", "domain": domain}

        area = detect_area(text)
        if area not in REGIONS:
            return [], {"url": final_url, "status": "outside_area", "domain": domain}

        page_date = published_date_from_soup(soup, text)
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        inherited = title if any(w in title for w in AORI_WORDS) else ""

        signals = []
        for day, segment in split_detail_segments(text, page_date):
            sig = signal_from_segment(src, day, segment, inherited_context=inherited)
            if not sig:
                continue
            if sig.get("area") not in REGIONS:
                continue
            if sig.get("evidence_role") != "catch":
                continue
            if sig.get("type") not in ("shore", "boat", "raft"):
                continue
            # Search is discovery, not a trust source. Actual-page verification
            # can make it useful, but never above B without a dedicated adapter.
            sig["confidence"] = "B"
            sig["quality_score"] = min(70, int(sig.get("quality_score") or 0))
            sig["usable_for_decision"] = True
            sig["detail_url"] = final_url
            sig["url"] = final_url
            sig["evidence_scope"] = "search_verified_detail"
            sig["search_query_region"] = row.get("region")
            sig["search_discovery"] = True
            stable = "|".join([
                "search", final_url, sig.get("date") or "", sig.get("area") or "",
                sig.get("type") or "", sig.get("method") or "",
            ])
            sig["id"] = "search-signal-" + hashlib.sha1(stable.encode("utf-8")).hexdigest()[:16]
            signals.append(sig)

        return signals, {
            "url": final_url,
            "status": "accepted" if signals else "no_usable_signal",
            "domain": domain,
            "area": area,
            "signals": len(signals),
        }
    except Exception as exc:
        return [], {
            "url": url, "status": "error", "domain": domain,
            "error": f"{type(exc).__name__}: {exc}"[:220],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/search-signals.json")
    args = parser.parse_args()

    queries = []
    for region in REGIONS:
        for tmpl in QUERY_TEMPLATES:
            queries.append((region, tmpl.format(region=region, year=NOW.year)))

    found = []
    diagnostics = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = {pool.submit(yahoo_search, region, q): (region, q) for region, q in queries}
        for fut in as_completed(futs):
            region, q = futs[fut]
            try:
                rows = fut.result()
                diagnostics.append({"region": region, "query": q, "status": "ok", "results": len(rows)})
                found.extend(rows)
            except Exception as exc:
                diagnostics.append({"region": region, "query": q, "status": "error", "error": str(exc)[:180]})

    # strongest discovery hint per URL; actual page decides acceptance
    by_url = {}
    for row in found:
        old = by_url.get(row["url"])
        if old is None or candidate_score(row) > candidate_score(old):
            by_url[row["url"]] = row
    candidates = sorted(by_url.values(), key=candidate_score, reverse=True)[:MAX_FETCH]

    signals = []
    checks = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(verify, row): row["url"] for row in candidates}
        for fut in as_completed(futs):
            sigs, check = fut.result()
            signals.extend(sigs)
            checks.append(check)

    # URL/date/area/type/method compression
    by_session = {}
    for sig in signals:
        key = "|".join([
            sig.get("url") or "", sig.get("date") or "", sig.get("area") or "",
            sig.get("type") or "", sig.get("method") or "",
        ])
        old = by_session.get(key)
        richness = int(sig.get("quality_score") or 0) + int(bool(sig.get("count_mentions"))) * 3
        old_richness = -1 if old is None else int(old.get("quality_score") or 0) + int(bool(old.get("count_mentions"))) * 3
        if old is None or richness > old_richness:
            by_session[key] = sig
    signals = sorted(by_session.values(), key=lambda x: (x.get("date") or "", x.get("quality_score") or 0), reverse=True)

    payload = {
        "version": 1,
        "updated_at": NOW.isoformat(timespec="seconds"),
        "profile": "verified-search-reports",
        "query_count": len(queries),
        "query_ok": sum(x.get("status") == "ok" for x in diagnostics),
        "candidate_urls": len(candidates),
        "verified_pages": sum(x.get("status") == "accepted" for x in checks),
        "note": "検索結果は発見専用。元ページ本文を再取得し、対象海域・アオリイカ・日付・実釣文脈を確認したB信号だけを補助情報として使用。",
        "diagnostics": diagnostics,
        "checks": checks,
        "signals": signals,
    }
    p = Path(args.output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "queries": len(queries),
        "query_ok": payload["query_ok"],
        "candidates": len(candidates),
        "accepted_pages": payload["verified_pages"],
        "signals": len(signals),
        "shore": sum(x.get("type") == "shore" for x in signals),
        "boat": sum(x.get("type") in ("boat", "raft") for x in signals),
        "areas": {a: sum(x.get("area") == a for x in signals) for a in REGIONS},
        "sources": sorted({x.get("source") for x in signals if x.get("source")}),
    }, ensure_ascii=False))

    if payload["query_ok"] < 10:
        raise SystemExit("too many report discovery search failures")


if __name__ == "__main__":
    main()
