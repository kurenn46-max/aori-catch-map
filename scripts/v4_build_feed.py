#!/usr/bin/env python3
"""Build the V4 canonical live feed consumed by the app.

Inputs are deliberately independent:
- catches.json: strict/direct collector
- v4-hot-signals.json: 30-minute shore-first lane
- discovery-signals.json: slower broad/deep lane

The UI reads one canonical file. Evidence origin/confidence stays attached to
every row so more coverage never means invented precision.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
AREA_CENTERS = {
    "越前": (35.914, 135.991),
    "敦賀": (35.645, 136.055),
    "若狭": (35.495, 135.746),
    "舞鶴": (35.474, 135.386),
    "丹後": (35.650, 135.150),
}
MAX_DAYS = 30

def load(path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

def parse_day(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except Exception:
        return None

def age_days(s):
    d = parse_day(s)
    return (NOW.date() - d).days if d else 9999

def direct_row(x):
    row = dict(x)
    row["feed_origin"] = "direct"
    row["evidence_confidence"] = row.get("evidence_confidence") or ("B" if row.get("supplementary") else "A")
    row["quality_score"] = row.get("quality_score") or (72 if row.get("supplementary") else 95)
    row["supplementary"] = bool(row.get("supplementary"))
    row["source_mode"] = row.get("source_mode") or row.get("type")
    row["feed_seen_at"] = row.get("last_seen_at") or row.get("first_seen_at")
    return row

def signal_status(sig):
    neg = set(sig.get("negative_signals") or [])
    if "チェイス" in neg:
        return "chase_only"
    if any(x in neg for x in ("ボウズ", "坊主", "釣れない", "釣れず", "反応なし")):
        return "blank"
    if "見えイカ" in neg:
        return "sighting_only"
    return "catch"

def signal_row(sig, origin):
    area = sig.get("area")
    if area not in AREA_CENTERS:
        return None
    stype = sig.get("type")
    if stype not in ("shore", "boat", "raft"):
        return None
    if not sig.get("usable_for_decision") or sig.get("evidence_role") != "catch":
        return None
    if sig.get("confidence") not in ("A", "B"):
        return None
    url = sig.get("detail_url") or sig.get("url")
    if not url or not sig.get("date") or not sig.get("source"):
        return None
    lat, lng = AREA_CENTERS[area]
    key = "|".join([origin, str(sig.get("id") or ""), sig["date"], area, sig["source"], url])
    rid = "v4-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:18]
    mode = "shore" if stype == "shore" else "boat"
    mentions = [int(x) for x in (sig.get("count_mentions") or []) if isinstance(x, (int, float)) and 0 < int(x) < 500]
    title = f"{sig['source']} / {'岸' if mode == 'shore' else '船'}・信頼度{sig.get('confidence')}"
    if sig.get("bait_signals"):
        title += " / ベイト:" + "・".join(str(x) for x in sig.get("bait_signals")[:3])
    return {
        "id": rid,
        "date": sig["date"],
        "area": area,
        "place": area,
        "lat": lat,
        "lng": lng,
        "type": mode,
        "source_mode": stype,
        "method": sig.get("method") or ("エギング" if mode == "shore" else "ティップラン"),
        "count": None,
        "count_mentions": mentions,
        "count_confidence": sig.get("count_confidence") or "none",
        "maxSize": "不明",
        "time": sig.get("time_mode") or "不明",
        "source": sig["source"],
        "url": url,
        "title": title,
        "demo": False,
        "precision": "area",
        "result_status": signal_status(sig),
        "first_seen_at": sig.get("first_seen_at"),
        "last_seen_at": sig.get("last_seen_at"),
        "feed_seen_at": sig.get("collected_at"),
        "feed_origin": origin,
        "origin_signal_id": sig.get("id"),
        "evidence_confidence": sig.get("confidence"),
        "quality_score": int(sig.get("quality_score") or 0),
        "supplementary": True,
        "bait_signals": sig.get("bait_signals") or [],
        "negative_signals": sig.get("negative_signals") or [],
        "depth_m": sig.get("depth_m") or [],
        "bottom_offset_m": sig.get("bottom_offset_m") or [],
        "tana_m": sig.get("tana_m") or [],
        "time_mode": sig.get("time_mode") or "unknown",
    }

def identity(row):
    # detail URL is the strongest identity for public reports. Direct catches can
    # share an area URL, so their own stable id remains part of the key.
    if row.get("feed_origin") == "direct" and not row.get("supplementary"):
        return "direct|" + str(row.get("id"))
    return "|".join([
        str(row.get("date") or ""),
        str(row.get("area") or ""),
        str(row.get("type") or ""),
        str(row.get("source") or ""),
        str(row.get("url") or ""),
    ])

def richness(row):
    return (
        int(row.get("feed_origin") == "hot") * 15
        + int(row.get("evidence_confidence") == "A") * 15
        + int(row.get("quality_score") or 0)
        + int(bool(row.get("count_mentions"))) * 4
        + int(bool(row.get("bait_signals"))) * 2
    )

def health_check(source, status, lane, **extra):
    out = {"source": source, "status": status, "lane": lane}
    out.update({k: v for k, v in extra.items() if v not in (None, "")})
    return out

def main():
    direct = load("data/catches.json", {"catches": []})
    hot = load("data/v4-hot-signals.json", {"signals": [], "source_health": []})
    broad = load("data/discovery-signals.json", {"signals": [], "source_health": []})
    direct_health = load("data/source-status.json", {"checks": []})

    candidates = []
    for x in direct.get("catches", []):
        if 0 <= age_days(x.get("date")) <= MAX_DAYS and not x.get("demo"):
            candidates.append(direct_row(x))

    for origin, doc in (("hot", hot), ("broad", broad)):
        for sig in doc.get("signals", []):
            if not (0 <= age_days(sig.get("date")) <= MAX_DAYS):
                continue
            row = signal_row(sig, origin)
            if row:
                candidates.append(row)

    by_id = {}
    for row in candidates:
        key = identity(row)
        old = by_id.get(key)
        if old is None or richness(row) > richness(old):
            by_id[key] = row

    rows = list(by_id.values())
    rows.sort(
        key=lambda x: (
            x.get("date") or "",
            int(x.get("type") == "shore"),
            int(x.get("evidence_confidence") == "A"),
            int(x.get("quality_score") or 0),
        ),
        reverse=True,
    )

    # Keep direct raw rows plus trusted supplementary evidence. A separate field
    # lets the UI and scoring distinguish confirmed/direct from area-level web evidence.
    counts = {
        "total": len(rows),
        "shore": sum(x.get("type") == "shore" for x in rows),
        "boat": sum(x.get("type") == "boat" for x in rows),
        "direct": sum(x.get("feed_origin") == "direct" and not x.get("supplementary") for x in rows),
        "supplementary": sum(bool(x.get("supplementary")) for x in rows),
        "hot": sum(x.get("feed_origin") == "hot" for x in rows),
        "broad": sum(x.get("feed_origin") == "broad" for x in rows),
    }
    latest_shore = max((x.get("date") for x in rows if x.get("type") == "shore"), default=None)

    checks = []
    for x in direct_health.get("checks", []):
        checks.append(health_check(x.get("source") or "direct", x.get("status") or "unknown", "direct",
                                   checked_at=x.get("checked_at"), candidate_count=x.get("candidate_count")))
    for lane, doc in (("hot", hot), ("broad", broad)):
        for x in doc.get("source_health", []):
            checks.append(health_check(x.get("source") or "unknown", x.get("status") or "unknown", lane,
                                       checked_at=x.get("checked_at"), accepted_signals=x.get("accepted_signals"),
                                       detail_signals=x.get("detail_signals"), error=x.get("error")))

    ok_status = {"ok", "no_new"}
    health = {
        "version": 4,
        "updated_at": NOW.isoformat(timespec="seconds"),
        "architecture": "direct + 30min hot shore + broad deep -> canonical live-feed",
        "target_hot_refresh_minutes": 30,
        "feed_counts": counts,
        "latest_shore_date": latest_shore,
        "latest_shore_age_days": age_days(latest_shore) if latest_shore else None,
        "checks": checks,
        "lanes": {
            "direct": {"updated_at": direct.get("updated_at")},
            "hot": {"updated_at": hot.get("updated_at"), "sources": len(hot.get("source_health", []))},
            "broad": {"updated_at": broad.get("updated_at"), "sources": len(broad.get("source_health", []))},
        },
        "coverage": {
            "checks_total": len(checks),
            "checks_ok": sum(x.get("status") in ok_status for x in checks),
            "checks_bad": sum(x.get("status") in {"blocked", "error"} for x in checks),
        },
    }
    payload = {
        "version": 4,
        "updated_at": NOW.isoformat(timespec="seconds"),
        "source_updated_at": {
            "direct": direct.get("updated_at"),
            "hot": hot.get("updated_at"),
            "broad": broad.get("updated_at"),
        },
        "note": "V4 canonical live feed. Direct reports and trusted A/B public evidence are merged without inventing exact counts or exact spots.",
        "counts": counts,
        "catches": rows[:700],
    }
    Path("data/live-feed.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path("data/v4-health.json").write_text(json.dumps(health, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"feed": counts, "latest_shore": latest_shore, "checks": health["coverage"]}, ensure_ascii=False))

    if not rows:
        raise SystemExit("V4 live feed is empty")
    if counts["shore"] == 0:
        raise SystemExit("V4 live feed has no shore evidence")

if __name__ == "__main__":
    main()
