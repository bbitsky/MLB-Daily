# Recovery — "database is empty" on train (2026-07-03)

## Root cause
The July 2 DB corruption wiped the `games`, `starters`, and `odds` tables (verified: `games=0, starters=0, odds=0, picks=28`). `mlb_train.py` builds its training set from the **`games`** table, so with 0 games there is nothing to train on → "database is empty".

The 2018–2020 odds `.xlsx` files do **not** fix this. `load_odds.py` is a library read by `clv_report.py` (closing-line-value analysis only) — running it does **not** insert anything into the DB, and odds are not training inputs. Training needs game **results + starters**, which come from the MLB Stats API build.

## Fix — run these on Windows, in order
The MLB Stats API is 403-blocked in the Cowork sandbox, so the `--build` step must run on your machine.

```bat
cd /d "C:\Users\bitsk\Claude\Projects\MLB Daily"

:: 1) Repopulate games + starters from the MLB Stats API (this is the missing step)
python mlb_data.py --build --seasons 2021 2022 2023 2024 2025 2026

:: 2) Backfill feature columns (streaks, day/night, OPS, defense) onto those games
python mlb_backfill.py --seasons 2021 2022 2023 2024 2025 2026

:: 3) Retrain
python mlb_train.py
```

Check after step 1 that games landed:
```bat
python -c "import sqlite3, mlb_data as m; c=sqlite3.connect(m.DB_PATH); print('games:', c.execute('select count(*) from games').fetchone()[0])"
```
Expect several thousand rows. If it's still 0, the API pull failed — re-run step 1 and watch its log.

`run_weekly.bat` already does `--build --seasons 2026` + retrain; the only difference above is building the full multi-year history the corruption erased, not just 2026.

## About the odds files (optional, separate from training)
The 2018–2020 odds only matter for `clv_report.py`, and only for seasons that also exist in `games`. Since the standard training window is 2021–25, 2018–2020 odds won't line up with any games unless you also `--build --seasons 2018 2019 2020`. Skip for now unless you specifically want CLV on those years.

## Two things I already fixed for you
- **Restored `data/mlb.db`** — the synced backup had gone malformed again (FUSE write-back). Restored from a clean in-session copy: integrity **ok**, 28 picks intact, today's Cardinals +106 pick present. The corrupt file was kept as `data/mlb.db.corrupt-<time>`. (Your live working DB is `%LOCALAPPDATA%\MLB-Daily\mlb.db`; this only restores the synced backup.)

## Known blocker to fix while you're in there
- **`mlb_train.py` won't compile on the synced copy** — `SyntaxError: '(' was never closed` around the `away_xfip_norm` line (~567–570), and the file is truncated at 569 lines (missing the rest of `predict_game` + the train entrypoint). This is FUSE sync lag — your Windows copy is presumably complete (it reached the "empty" check). If your Windows copy shows the same truncation, restore `mlb_train.py` from git or re-save it, because a truncated train script will fail regardless of the DB.
