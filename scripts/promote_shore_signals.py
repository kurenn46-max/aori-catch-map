#!/usr/bin/env python3
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

def load(path, default):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))

def main():
    catches_doc = load("data/catches.json", {"catches": []})
    discovery = load("data/discovery-signals.json", {"signals": []})
    rows = catches_doc.get("catches", [])
    signals = discovery.get("signals", [])

    existing_ids = {str(x.get("id")) for x in rows if x.get("id")}
    existing_keys = {
        (
            x.get("date"),
            x.get("area"),
            x.get("type"),
            x.get("source"),
            x.get("url"),
        )
        for x in rows
    }

    promoted = []
    for sig in signals:
        if not sig.get("usable_for_decision"):
            continue
        if sig.get("evidence_role") != "catch":
            continue
        if sig.get("type") != "shore":
            continue
        if sig.get("confidence") not in ("A", "B"):
            continue
        area = sig.get("area")
        if area not in AREA_CENTERS:
            continue
        date = sig.get("date")
        source = sig.get("source")
        url = sig.get("detail_url") or sig.get("url")
        if not date or not source or not url:
            continue

        rid = "shore-signal-" + str(sig.get("id", "")).replace("signal-", "")
        key = (date, area, "shore", source, url)
        if rid in existing_ids or key in existing_keys:
            continue

        lat, lng = AREA_CENTERS[area]
        bait = sig.get("bait_signals") or []
        title = f"{source} / 外部確認済み岸釣果"
        if bait:
            title += " / ベイト:" + "・".join(str(x) for x in bait[:3])

        row = {
            "id": rid,
            "date": date,
            "area": area,
            "place": area,
            "lat": lat,
            "lng": lng,
            "type": "shore",
            "method": sig.get("method") or "エギング",
            "count": None,
            "maxSize": "不明",
            "time": "不明",
            "source": source,
            "url": url,
            "title": title,
            "demo": False,
            "precision": "area",
            "result_status": "catch",
            "first_seen_at": discovery.get("updated_at") or NOW.isoformat(timespec="seconds"),
            "last_seen_at": discovery.get("updated_at") or NOW.isoformat(timespec="seconds"),
            "origin": "discovery-signal",
            "origin_signal_id": sig.get("id"),
            "evidence_confidence": sig.get("confidence"),
            "quality_score": sig.get("quality_score"),
            "supplementary": True,
        }
        promoted.append(row)
        existing_ids.add(rid)
        existing_keys.add(key)

    if promoted:
        rows.extend(promoted)
        rows.sort(key=lambda x: (x.get("date") or "", x.get("time") or ""), reverse=True)
        catches_doc["catches"] = rows[:500]
        catches_doc["updated_at"] = NOW.isoformat(timespec="seconds")
        catches_doc["note"] = (
            "GitHub Actions自動収集。エギCOM直取得に加え、A/B評価の公開Web横断岸釣果を"
            "supplementary=trueで補助表示。補助釣果は杯数不明のまま保持し、攻略A/B/Cへ直接加点しない。"
        )
        Path("data/catches.json").write_text(
            json.dumps(catches_doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"promoted_shore_signals={len(promoted)} total_catches={len(catches_doc.get('catches', []))}")

if __name__ == "__main__":
    main()
