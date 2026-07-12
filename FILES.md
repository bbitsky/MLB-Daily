# MLB Daily — File Guide

_What each file does, when to run it, and whether it's safe to delete. Generated 2026-07-02._

## Core engine (keep — imported by everything, don't run directly)

| File | What it does | Run? |
|------|--------------|------|
| `mlb_data.py` | Data layer: MLB Stats API + Odds API + pybaseball, DB schema, `DB_PATH`, odds/weather/lineup fetches. | Only `python mlb_data.py --build` to (re)build the 2021–25 training dataset. |
| `mlb_dashboard.py` | Builds the HTML dashboard and the plain-language game "reasons". | Imported by run scripts; not run directly. |
| `mlb_results.py` | Grades W/L, pick record, bankroll math. | Imported. |
| `mlb_intel.py` | Betting/social intel: weather, sharp money, line movement, umpire, situational, injuries, BvP. | Imported. |
| `mlb_model.py` | Older v2.1 model logic (11-step). Largely superseded by the v3 XGBoost/formula path. | Legacy — keep for reference, safe to archive. |
| `mlb_train.py` | Trains the v3 XGBoost model → `data/mlb_model.pkl`. | Occasionally (weekly) to retrain. |

## Daily / weekly run scripts (keep the ones you use)

| File | What it does | When to run |
|------|--------------|-------------|
| `run_daily.bat` / `run_daily.py` | Logs yesterday's results, regenerates the dashboard (now with live intel). | Every morning. |
| `mlb_daily.py` | Prints today's model picks/parlays to the console (no dashboard). | Optional, for a quick console look. |
| `build_july2.py` | Manual slate injector — hardcodes a day's games/odds/pitchers and builds the picks+intel dashboard. **This is your per-day template.** | Copy to `build_<month><day>.py`, edit the SLATE, run when the APIs are blocked. |
| `run_results.bat` | Just logs yesterday's results. | Optional. |
| `run_weekly.bat` | Weekly data pull + retrain. | Weekly. |
| `run_train.bat` | Runs `mlb_train.py`. | When retraining. |
| `push_to_github.bat` | Deploys the dashboard to GitHub Pages (fixed to use the token + correct format). | After generating a dashboard. |
| `deploy_dashboard.py` | Alternate Python deploy to GitHub Pages. Overlaps with `push_to_github.bat`. | Redundant — pick one. |
| `sync_bets.py` | Imports your `my_bets.json` (with $ amounts) into the DB. | After clicking "Save my bets to file". |
| `repair_mlb_db.py` | Rebuilds a corrupt `data/mlb.db` from `picks_history_backup.csv`. | Only when the DB is malformed. |

## Reference docs (keep)

| File | What it is |
|------|-----------|
| `mlb_model_assessment_june26_2026.md`, `mlb_model_v2_june28_2026.md` | Model methodology / assessment. |
| `NEXT_BUILD.md` | Notes for a future in-game live-odds model. |
| `TRIGGERS_AUDIT.md` | Reasons/trigger audit notes. |
| `.env` | **Secret** — API keys + GitHub token. Never commit or delete. |
| `.gitignore`, `requirements.txt` | Config. |

## One-time scripts — safe to delete once they've run

- `mlb_backfill.py` — one-time feature-column backfill.
- `backfill_bullpen.py` — one-time bullpen-ERA backfill.
- `run_backfill.bat` — runs the above.
- `setup_github_pages.bat` — one-time initial Pages setup.

## Junk / test artifacts — safe to delete now

- `_umptest.py` — just a copy of `build_july1.py`.
- `debug_dashboard.py`, `debug_output.txt` (empty), `run_output.txt`, `_synccheck.txt`, `auto_run_2026-07-01.md` — scratch/log files.
- `__pycache__/` — compiled cache; deleting it also clears the stale/corrupt `.pyc` that caused the earlier import errors (Python rebuilds it).
- `build_july1.py` — last-day's slate; keep only if you want the example, else delete (`build_july2.py` is the current template).
- `mlb_dashboard_redesign.html`, `mlb_dashboard_preview.html` — drafts/previews; regenerate anytime.
- `mlb_picks_june26_2026.md.pdf` — one-off PDF export.
- `joblib_stub/` — import shim; keep **only** if a script fails importing `joblib`, otherwise deletable.

## Dated outputs — archival, delete old ones to declutter

- `mlb_dashboard_2026-06-29 … 07-02.html` — daily dashboard snapshots. The live copy lives on GitHub Pages; keep the last couple, delete older.
- `mlb_report_*.md`, `mlb_picks_*.md`, `picks_june30_2026.md` — dated reports; keep for records or delete.

## Data folder — **be careful**

| File | Keep? |
|------|-------|
| `data/mlb.db` | **KEEP — this is the live database.** |
| `data/mlb_model.pkl` | **KEEP** — trained model. |
| `data/mlb_metrics.json`, `data/picks_history_backup.csv` | KEEP. |
| `data/mlb.db.corrupt-2026-07-01`, `…-20260701_183411`, `…-20260702_020734` | **DELETE** — ~14 MB of corrupt crash backups. |
| `data/mlb.db.bak`, `data/mlb_repaired.db`, top-level `mlb_repaired.db` | Delete — malformed repair artifacts. |
| `data/mlb_recovered.db` (0 bytes) | Delete — empty. |
| `data/data` (symlink) | **DELETE** — broken link to a dead session path. |
| `picks_history_backup.pre-july1.csv` | Delete — superseded by `picks_history_backup.csv`. |

**Biggest quick win:** deleting the three `data/*.corrupt-*` files + `mlb_repaired.db` copies reclaims ~28 MB and removes confusing dead databases.
