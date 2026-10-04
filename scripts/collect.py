#!/usr/bin/env python3
import json
import re
import hashlib
import html
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
MAX_DAYS = 30

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
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.7,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
        )
    ),
)

YAMARIA = [
    ("越前", "越前", 86, 35.914, 135.991),
    ("敦賀", "敦賀", 85, 35.645, 136.055),
    ("若狭", "小浜", 84, 35.495, 135.746),
    ("舞鶴", "舞鶴", 114, 35.474, 135.386),
    ("丹後", "丹後", 115, 35.650, 135.150),
]

POINTS = {
    "越前海岸": (35.914, 135.991),
    "越前岬": (35.980, 135.958),
    "甲楽城": (35.827, 136.020),
    "敦賀湾": (35.681, 136.049),
    "常神": (35.608, 135.833),
    "常神半島": (35.608, 135.833),
    "小浜": (35.495, 135.746),
    "小浜湾": (35.521, 135.720),
    "高浜": (35.489, 135.551),
    "白杉": (35.500, 135.337),
    "舞鶴": (35.474, 135.386),
    "舞鶴湾": (35.507, 135.376),
    "伊根": (35.674, 135.287),
    "宮津": (35.535, 135.196),
    "京丹後": (35.650, 135.060),
}

POST_RE = re.compile(
    r"(?P<hits>\d+)\s*HIT\s+"
    r"(?P<user>.+?)\s+さん\s+"
    r"(?P<date>20\d{2}-\d{2}-\d{2})\s+"
    r"(?P<time>\d{1,2}:\d{2})\s+"
    r"アオリイカ：\s*(?P<size>\S+)\s+"
    r"釣果場所：\s*(?P<pref>\S+)\s+(?P<reported_place>\S+)\s+"
    r"釣り場所：\s*(?P<fish_place>\S+)"
)


def clean(value):
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def age_ok(date_s):
    try:
        d = datetime.strptime(date_s, "%Y-%m-%d").replace(tzinfo=JST)
    except ValueError:
        return False
    age = (NOW.date() - d.date()).days
    return 0 <= age <= MAX_DAYS


def fingerprint(row):
    return (
        row.get("date"),
        row.get("area"),
        row.get("place"),
        row.get("type"),
        row.get("time"),
        row.get("source"),
        row.get("maxSize"),
    )


def parse_post(match, area, fallback_place, lat, lng, city_url, detail_url=None):
    date_s = match.group("date")
    if not age_ok(date_s):
        return None

    user = clean(match.group("user"))
    tm = match.group("time").zfill(5)
    size = clean(match.group("size"))
    reported_place = clean(match.group("reported_place"))
    fish_place = clean(match.group("fish_place"))

    typ = "boat" if any(k in fish_place for k in ("ボート", "船")) else "shore"
    method = "ティップラン" if typ == "boat" else "エギング"
    shown_place = reported_place if reported_place not in ("福井", "京都") else fallback_place
    plat, plng = POINTS.get(shown_place, (lat, lng))

    source_url = detail_url or city_url
    stable = f"{source_url}|{date_s}|{tm}|{user}|{size}|{fish_place}"
    rid = "yamaria-" + hashlib.sha1(stable.encode("utf-8")).hexdigest()[:16]

    return {
        "id": rid,
        "date": date_s,
        "area": area,
        "place": shown_place,
        "lat": plat,
        "lng": plng,
        "type": typ,
        "method": method,
        "count": None,
        "maxSize": size,
        "time": tm,
        "source": "エギCOM",
        "url": source_url,
        "title": f"{user}さん / {fish_place}",
        "demo": False,
        "precision": "area",
        "result_status": "catch",
        "reportPlace": fish_place,
        "first_seen_at": NOW.isoformat(timespec="seconds"),
        "last_seen_at": NOW.isoformat(timespec="seconds"),
    }


def yamaria_rows(area, place, city_id, lat, lng):
    city_url = f"https://www.yamaria.com/community/catch/egiou/cities/{city_id}"
    checked_at = NOW.isoformat(timespec="seconds")
    label = f"エギCOM / {place}"

    try:
        response = SESSION.get(city_url, timeout=(10, 35))
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        rows = []
        seen = set()
        anchors_examined = 0

        for anchor in soup.find_all("a", href=True):
            raw = clean(anchor.get_text(" ", strip=True))
            if "アオリイカ：" not in raw or "釣果場所：" not in raw:
                continue
            anchors_examined += 1
            match = POST_RE.search(raw)
            if not match:
                continue
            detail_url = urljoin(city_url, anchor.get("href", ""))
            row = parse_post(match, area, place, lat, lng, city_url, detail_url)
            if not row:
                continue
            fp = fingerprint(row)
            if fp not in seen:
                seen.add(fp)
                rows.append(row)

        fallback_used = False
        if not rows:
            page_text = clean(soup.get_text(" ", strip=True))
            for match in POST_RE.finditer(page_text):
                row = parse_post(match, area, place, lat, lng, city_url)
                if not row:
                    continue
                fallback_used = True
                fp = fingerprint(row)
                if fp not in seen:
                    seen.add(fp)
                    rows.append(row)

        visible_text = clean(soup.get_text(" ", strip=True))
        has_expected_page = "最新釣果投稿" in visible_text
        status = "ok" if rows else ("no_new" if has_expected_page else "error")
        note_parts = [
            f"HTTP {response.status_code}",
            f"解析 {len(rows)}件",
            f"候補リンク {anchors_examined}件",
        ]
        if fallback_used:
            note_parts.append("全文fallback使用")
        if not has_expected_page:
            note_parts.append("期待見出し未検出")

        print(f"{label}: parsed={len(rows)} anchors={anchors_examined} fallback={fallback_used}")
        return rows, {
            "source": label,
            "url": city_url,
            "checked_at": checked_at,
            "status": status,
            "new_count": 0,
            "candidate_count": len(rows),
            "note": " / ".join(note_parts),
        }
    except Exception as exc:
        print(f"WARN {label}: {exc}")
        return [], {
            "source": label,
            "url": city_url,
            "checked_at": checked_at,
            "status": "error",
            "new_count": 0,
            "candidate_count": 0,
            "note": f"{type(exc).__name__}: {exc}"[:240],
        }


def load_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"WARN JSON read {path}: {exc}")
        return default


def write_json(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    candidates = []
    checks = []

    for args in YAMARIA:
        rows, check = yamaria_rows(*args)
        checks.append(check)
        for row in rows:
            candidates.append((row, check["source"]))

    # GitHub-hosted runners can receive a stripped Yamaria page that still
    # returns HTTP 200 and the section heading but no catch cards. Five regions
    # becoming empty at the same time is treated as access blocking, not
    # evidence that there were no new catches.
    if checks and all(
        x.get("status") == "no_new" and int(x.get("candidate_count", 0)) == 0
        for x in checks
    ):
        for x in checks:
            x["status"] = "blocked"
            x["note"] += " / 5地域同時0件: GitHub Runnerへの本文省略・取得制限疑い"

    current = load_json("data/catches.json", {"catches": []})
    existing = current.get("catches", [])

    by_id = {}
    fingerprints = set()
    for row in existing:
        key = row.get("id") or hashlib.sha1(repr(fingerprint(row)).encode("utf-8")).hexdigest()
        by_id[str(key)] = row
        fingerprints.add(fingerprint(row))

    added = 0
    added_by_source = {}
    for row, source_label in candidates:
        rid = str(row["id"])
        fp = fingerprint(row)
        if rid in by_id or fp in fingerprints:
            continue
        by_id[rid] = row
        fingerprints.add(fp)
        added += 1
        added_by_source[source_label] = added_by_source.get(source_label, 0) + 1

    for check in checks:
        check["new_count"] = added_by_source.get(check["source"], 0)
        if check["status"] == "ok" and check["new_count"] == 0:
            check["status"] = "no_new"

    cutoff = (NOW - timedelta(days=MAX_DAYS)).date().isoformat()
    final = [row for row in by_id.values() if row.get("date", "") >= cutoff]
    final.sort(key=lambda x: (x.get("date", ""), x.get("time", ""), x.get("id", "")), reverse=True)

    write_json(
        "data/catches.json",
        {
            "updated_at": NOW.isoformat(timespec="seconds"),
            "note": (
                "GitHub Actions自動収集。確認済み既存データを保持し、"
                "エギCOMの直近投稿を重複排除して追記。"
            ),
            "catches": final[:500],
        },
    )

    write_json(
        "data/source-status.json",
        {
            "updated_at": NOW.isoformat(timespec="seconds"),
            "collector": "github-actions-core-v2",
            "note": (
                "コア自動収集の巡回結果。現在はエギCOM5地域を直接監視。"
                "その他のA/B優先情報源はChatGPT補完巡回で追加確認する。"
            ),
            "fallback": {
                "enabled": True,
                "mode": "chatgpt-public-web",
                "schedule": "6時間ごと",
                "reason": "GitHub Runnerで本文が省略される場合に公開Web経路で補完",
            },
            "checks": checks,
        },
    )

    errors = [x for x in checks if x["status"] == "error"]
    parsed = sum(int(x.get("candidate_count", 0)) for x in checks)
    print(
        f"Collector summary: candidates={parsed} added={added} "
        f"display_total={len(final[:500])} errors={len(errors)}"
    )

    if checks and len(errors) == len(checks):
        raise SystemExit("All direct Yamaria sources failed. Collector aborted as unhealthy.")


if __name__ == "__main__":
    main()
