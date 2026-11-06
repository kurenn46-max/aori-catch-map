# Aori catch map automation paused

**Paused on:** 2026-11-07 (JST)

This repository and its GitHub Pages site remain intact. Existing code, history,
and catch data have **not** been deleted. Automatic data collection and automatic
Pages publishing were intentionally paused because this app is not currently in use.

## Workflows changed to manual-only

| Workflow file | Previous automatic trigger |
| --- | --- |
| `.github/workflows/v4-fast-refresh.yml` | Every 30 minutes; V4 branch pushes |
| `.github/workflows/collect.yml` | Every 4 hours; selected main-branch pushes |
| `.github/workflows/discover-sources.yml` | Daily source discovery |
| `.github/workflows/tides.yml` | Daily JMA tide update; relevant pushes |
| `.github/workflows/tide-patterns.yml` | Selected data and source pushes |
| `.github/workflows/pages.yml` | Main pushes; successful collector workflow runs |

All six still have `workflow_dispatch`, so their jobs can be started manually
from GitHub **Actions** > the workflow > **Run workflow** (branch: `main`).

## Resume later

1. Decide which collectors and data sources should be used again; validate
   their data rights and reliability before resuming collection.
2. Restore the desired `schedule` and/or `push` / `workflow_run` triggers
   from the commit history before this pause (do not blindly re-enable everything).
3. Review / test the changes in a pull request before merging to `main`.
4. Run **Deploy GitHub Pages** manually if publication is needed.

This pause does **not** disable code/PR tests, manual catch issue handling,
or other on-demand checks, and does not change GitHub notification preferences.
Other repositories and projects are unaffected.
