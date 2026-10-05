#!/usr/bin/env python3
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 16; Mobile) AppleWebKit/537.36 Chrome/141 Mobile Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
}

REGIONS = ["越前", "敦賀", "若狭", "小浜", "舞鶴", "丹後"]
QUERY_TEMPLATES = [
    "{region} アオリイカ ティップラン 遊漁船 船長ブログ",
    "{region} アオリイカ ティップラン 水深 ボトム 釣果",
    "{region} アオリイカ 釣果 船 マリーナ ブログ",
]
SEARCH_EXCLUSIONS = (
    "-site:anglers.jp -site:fishing.ne.jp -site:johshuya.co.jp "
    "-site:bunbun-fishing.com -site:yamaria.com -site:fishing-v.jp"
)
TARGET_WORDS = ("アオリ", "ティップラン", "エギング")
NOISE_DOMAINS = {
    "www.google.com","google.com","www.bing.com","bing.com","duckduckgo.com",
    "www.youtube.com","youtube.com","m.youtube.com","x.com","twitter.com",
    "www.facebook.com","facebook.com","instagram.com","www.instagram.com",
}
KNOWN_FILE = Path("data/source-registry.json")


def norm_host(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def registrableish(host):
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    # pragmatic grouping for common Japanese domains
    if len(parts) >= 3 and parts[-2] in {"co","ne","or","ac","go"} and parts[-1] == "jp":
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def known_domains():
    if not KNOWN_FILE.exists():
        return set()
    data = json.loads(KNOWN_FILE.read_text(encoding="utf-8"))
    out = set()
    for src in data.get("sources", []):
        h = norm_host(src.get("url") or "")
        if h:
            out.add(registrableish(h))
    return out


def score_item(title, snippet, url, region):
    text = f"{title} {snippet} {url}"
    score = 0
    reasons = []
    if region in text:
        score += 20; reasons.append("region")
    if "アオリ" in text:
        score += 30; reasons.append("aori")
    if "ティップラン" in text:
        score += 20; reasons.append("tiprun")
    if "エギング" in text:
        score += 10; reasons.append("eging")
    if "水深" in text or re.search(r"\b\d{1,2}\s*m\b", text, re.I):
        score += 15; reasons.append("depth")
    if "釣果" in text:
        score += 10; reasons.append("catch")
    if any(w in text for w in ("遊漁船","釣り船","船長","マリーナ","渡船")):
        score += 15; reasons.append("boat_source")
    if any(w in text for w in ("ブログ","釣行記","釣果情報")):
        score += 8; reasons.append("report_source")
    if any(w in text for w in ("予約","料金","募集")) and "釣果" not in text:
        score -= 10; reasons.append("promo_penalty")
    return max(0, min(100, score)), reasons


def bing_rss(query):
    url = "https://www.bing.com/search?format=rss&q=" + quote_plus(query)
    r = requests.get(url, headers=HEADERS, timeout=(7, 18))
    r.raise_for_status()
    root = ET.fromstring(r.content)
    rows = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ", strip=True)
        if link:
            rows.append({"title": title, "url": link, "snippet": desc[:500], "engine": "bing_rss"})
    return rows


def ddg_html(query):
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    r = requests.get(url, headers=HEADERS, timeout=(7, 18))
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    rows = []
    for result in soup.select(".result"):
        a = result.select_one(".result__a")
        if not a:
            continue
        href = a.get("href") or ""
        parsed = urlparse(href)
        if "duckduckgo.com" in (parsed.hostname or ""):
            uddg = parse_qs(parsed.query).get("uddg", [])
            if uddg:
                href = unquote(uddg[0])
        snippet_el = result.select_one(".result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        rows.append({
            "title": a.get_text(" ", strip=True),
            "url": href,
            "snippet": snippet[:500],
            "engine": "ddg_html",
        })
    return rows


def main():
    known = known_domains()
    engines = [bing_rss, ddg_html]
    diagnostics = []
    candidates = {}

    queries = []
    # Balanced: 3 long-tail queries for every region, instead of exhausting
    # early regions first. Exclude large known platforms to surface small
    # charter/marina/blog domains that fixed-source crawling would miss.
    for tmpl in QUERY_TEMPLATES:
        for region in REGIONS:
            queries.append((region, f"{tmpl.format(region=region)} {SEARCH_EXCLUSIONS}"))

    for region, query in queries:
        for engine in engines:
            try:
                rows = engine(query)
                diagnostics.append({"query": query, "engine": engine.__name__, "status": "ok", "results": len(rows)})
            except Exception as exc:
                diagnostics.append({
                    "query": query, "engine": engine.__name__, "status": "error",
                    "error": f"{type(exc).__name__}: {exc}"[:240],
                })
                continue

            for row in rows[:12]:
                host = norm_host(row["url"])
                if not host or host in NOISE_DOMAINS:
                    continue
                domain = registrableish(host)
                score, reasons = score_item(row["title"], row["snippet"], row["url"], region)
                key = row["url"].split("#", 1)[0]
                cur = candidates.get(key)
                record = {
                    "url": key,
                    "domain": domain,
                    "host": host,
                    "title": row["title"][:220],
                    "snippet": row["snippet"][:360],
                    "region": region,
                    "query": query,
                    "engine": row["engine"],
                    "score": score,
                    "reasons": reasons,
                    "known_domain": domain in known,
                }
                if cur is None or score > cur["score"]:
                    candidates[key] = record

    rows = sorted(candidates.values(), key=lambda x: (x["known_domain"], -x["score"], x["domain"], x["url"]))
    new_rows = [x for x in rows if not x["known_domain"] and x["score"] >= 40]
    domain_counts = Counter(x["domain"] for x in new_rows)

    payload = {
        "checked_at": NOW.isoformat(timespec="seconds"),
        "query_count": len(queries),
        "diagnostics": diagnostics,
        "candidate_count": len(rows),
        "new_candidate_count": len(new_rows),
        "new_domain_count": len(domain_counts),
        "new_domain_counts": dict(domain_counts.most_common()),
        "new_candidates": new_rows[:120],
    }

    print(json.dumps({
        "query_count": payload["query_count"],
        "engine_ok": sum(x["status"] == "ok" for x in diagnostics),
        "engine_error": sum(x["status"] == "error" for x in diagnostics),
        "candidate_count": payload["candidate_count"],
        "new_candidate_count": payload["new_candidate_count"],
        "new_domain_count": payload["new_domain_count"],
        "top_new_domains": domain_counts.most_common(15),
    }, ensure_ascii=False, indent=2))

    out = Path("test-results/keyword-source-discovery.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not any(x["status"] == "ok" and x.get("results", 0) > 0 for x in diagnostics):
        raise SystemExit("no search engine returned results")
    if not rows:
        raise SystemExit("no candidates discovered")


if __name__ == "__main__":
    main()
