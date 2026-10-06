# Aori Catch Map V4 architecture

V4 keeps the current mobile UI concept but replaces the data path.

## Data lanes

1. **Direct lane** — `scripts/collect.py`
   - Structured first-party/public catch pages with stable identifiers.
   - Never treats blocked/empty HTML as zero catches.

2. **Hot shore lane** — `scripts/v4_collect_hot.py`
   - Small set of high-yield tackle-shop/public fishing sources.
   - Target cadence: every 30 minutes.
   - Uses the same evidence parser and A/B/C rules as the deep collector.

3. **Deep public lane** — `scripts/collect_public_signals.py`
   - Broad multi-source scan for shore, boat, bait, negative evidence and depth.
   - Lower cadence because it follows more detail pages.

4. **Source-growth lane** — `scripts/discover_sources.py`
   - Shore-first keyword discovery.
   - Search snippets are discovery only; an actual page must be fetched before a candidate can be A/B.
   - Candidate sources do not automatically become trusted collection sources.

## Canonical feed

`scripts/v4_build_feed.py` merges the direct, hot and deep lanes into
`data/live-feed.json`. The app reads this file first and falls back to the old
`data/catches.json` only if the V4 file is unavailable.

Each feed row keeps:

- evidence origin (`direct`, `hot`, `broad`)
- A/B evidence confidence
- source URL
- exact/area precision
- supplementary flag
- negative signals / bait signals / boat depth context when available

### Safety / quality invariants

- Never invent a catch count from an arbitrary number in article text.
- Supplementary public evidence keeps `count=null` unless a dedicated parser
  can prove the count belongs to Aori squid.
- Area-only evidence is displayed as area precision, never as an exact spot.
- Boat/raft evidence never becomes a shore session.
- Boat depth is context for shore planning, not a shore score multiplier.
- Publish date and actual trip date are separate; actual trip date wins.
- Blocked/unavailable sources are health failures, not negative fishing evidence.
- Listing/detail duplicates are session-compressed.

## Cadence

- V4 hot refresh: target every 30 minutes.
- Deep collection: every 4 hours.
- Source discovery: daily.
- GitHub Pages deploys automatically after generated-data commits on `main`.

The effective public-site-to-app latency is therefore normally bounded by the
hot refresh interval plus GitHub Actions/Pages deployment delay for sources in
the hot lane.

## UI

The existing mobile layout is retained. The catch map now reads
`data/live-feed.json` and visibly distinguishes direct vs supplementary rows.
The “latest sync” button re-reads published data; collection itself is automatic.
