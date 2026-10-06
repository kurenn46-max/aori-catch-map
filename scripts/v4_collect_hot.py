#!/usr/bin/env python3
"""V4 fast lane: poll only high-yield shore/public sources.

This lane is intentionally small enough to run every 30 minutes. It reuses the
same extraction and evidence rules as collect_public_signals.py, so the fast
path and deep path cannot disagree about A/B/C grading.
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from collect_public_signals import NOW, SOURCES, collect_one

HOT_NAMES = {
    "上州屋 新敦賀店",
    "ブンブン釣行記",
    "釣具のイシグロ",
}

EXTRA_SOURCES = [
    {
        "name": "FISHERS アオリイカ",
        "kind": "tackle_shop_media",
        "url": "https://www.fishers.co.jp/fishinginfo/?tsurikata_code=TKT0019",
        "default_area": None,
        "detail_patterns": [r"/fishinginfo/page\.html\?info_code=\d+", r"/fishinginfo/.*\d+"],
        "detail_limit": 18,
    },
    {
        "name": "アングラーズ日本海",
        "kind": "tackle_shop_media",
        "url": "https://www.anglers.co.jp/trends/",
        "default_area": None,
        "detail_patterns": [r"/trends/[^/]+/?$"],
        "detail_limit": 24,
    },
]

def richness(sig):
    return (
        int(bool(sig.get("detail_url"))) * 30
        + int(sig.get("evidence_scope") == "detail") * 20
        + int(sig.get("quality_score") or 0)
        + int(bool(sig.get("count_mentions"))) * 3
        + int(bool(sig.get("bait_signals"))) * 2
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/v4-hot-signals.json")
    args = parser.parse_args()

    selected = [x for x in SOURCES if x.get("name") in HOT_NAMES]
    # Override the generic FISHERS root with a fish-filtered page and add the
    # Anglers trends feed. The normal broad collector still keeps its wider set.
    selected.extend(EXTRA_SOURCES)

    all_signals, health = [], []
    with ThreadPoolExecutor(max_workers=min(6, len(selected))) as pool:
        futures = {pool.submit(collect_one, src): src["name"] for src in selected}
        for future in as_completed(futures):
            signals, status = future.result()
            all_signals.extend(signals)
            health.append(status)

    order = {src["name"]: i for i, src in enumerate(selected)}
    health.sort(key=lambda x: order.get(x.get("source"), 999))

    # One strongest item per source/day/area/mode/method/time. This prevents
    # list + detail duplication while preserving separate shore/boat sessions.
    by_session = {}
    for sig in all_signals:
        key = "|".join([
            str(sig.get("source") or ""),
            str(sig.get("date") or ""),
            str(sig.get("area") or ""),
            str(sig.get("type") or ""),
            str(sig.get("method") or ""),
            str(sig.get("time_mode") or ""),
        ])
        old = by_session.get(key)
        if old is None or richness(sig) > richness(old):
            by_session[key] = sig

    signals = sorted(
        by_session.values(),
        key=lambda x: (x.get("date") or "", int(x.get("quality_score") or 0)),
        reverse=True,
    )
    payload = {
        "version": 4,
        "profile": "shore-fast",
        "updated_at": NOW.isoformat(timespec="seconds"),
        "poll_target_minutes": 30,
        "note": "V4高速レーン。岸釣果を優先する少数の公開情報源だけを高頻度巡回し、A/B判定のみlive-feed候補にする。",
        "source_health": health,
        "signals": signals,
    }
    p = Path(args.output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    trusted_shore = [x for x in signals if x.get("type") == "shore" and x.get("usable_for_decision")]
    print(json.dumps({
        "sources": len(selected),
        "ok": sum(x.get("status") == "ok" for x in health),
        "signals": len(signals),
        "trusted_shore": len(trusted_shore),
        "latest_shore": trusted_shore[0].get("date") if trusted_shore else None,
    }, ensure_ascii=False))

    if not any(x.get("status") == "ok" for x in health):
        raise SystemExit("V4 hot lane: all sources failed")

if __name__ == "__main__":
    main()
