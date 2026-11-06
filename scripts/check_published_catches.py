#!/usr/bin/env python3
"""Post-deploy contract for the direct catch dataset.

An empty direct database is a *degraded source* state when no source returned
catch candidates; it is not a failed GitHub Pages deployment. V4 canonical
live-feed integrity is checked separately by the deploy workflow.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


class VerificationError(ValueError):
    """Data is missing, malformed or inconsistent with the source report."""


def verify(catches_doc, source_doc):
    if not isinstance(catches_doc, dict):
        raise VerificationError("catches.json must be a JSON object")
    stamp = catches_doc.get("updated_at")
    if not isinstance(stamp, str):
        raise VerificationError("catches.json updated_at missing")
    try:
        datetime.fromisoformat(stamp)
    except ValueError as exc:
        raise VerificationError("catches.json updated_at invalid") from exc

    rows = catches_doc.get("catches")
    if not isinstance(rows, list):
        raise VerificationError("catches.json catches must be a list")

    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise VerificationError("direct catch row is not an object")
        for key in ("id", "date", "area", "type", "source", "url"):
            if not row.get(key):
                raise VerificationError(f"direct catch row missing {key}")
        if row["id"] in ids:
            raise VerificationError("direct catch rows contain duplicate ids")
        ids.add(row["id"])

    if not isinstance(source_doc, dict) or not isinstance(source_doc.get("checks"), list):
        raise VerificationError("source-status.json checks missing or invalid")
    checks = source_doc["checks"]
    if not checks:
        raise VerificationError("source-status.json contains no source checks")

    if not rows:
        allowed = {"blocked", "error", "no_new"}
        for check in checks:
            if not isinstance(check, dict) or check.get("status") not in allowed:
                raise VerificationError("empty catches contradict source health")
            try:
                candidate_count = int(check.get("candidate_count", 0))
            except (TypeError, ValueError) as exc:
                raise VerificationError("invalid source candidate_count") from exc
            if candidate_count != 0:
                raise VerificationError("empty catches despite collected candidates")
        return "warning", "0 direct catches; all checked sources reported no candidates (blocked/error/no_new)"

    return "ok", f"{len(rows)} direct catches validated"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catches", required=True)
    parser.add_argument("--sources", required=True)
    args = parser.parse_args()
    try:
        catches = json.loads(Path(args.catches).read_text(encoding="utf-8"))
        sources = json.loads(Path(args.sources).read_text(encoding="utf-8"))
        status, message = verify(catches, sources)
    except (OSError, json.JSONDecodeError, VerificationError) as exc:
        print(f"::error::Published direct catches verification failed: {exc}", file=sys.stderr)
        return 1
    if status == "warning":
        print(f"::warning::{message}; V4 canonical feed is checked independently")
    else:
        print(message)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"- Direct catches: **{status}** — {message}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
