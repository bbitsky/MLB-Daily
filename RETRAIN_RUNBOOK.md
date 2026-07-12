# Model Review Fixes — Runbook (2026-07-05)

One-week review of the MLB model surfaced six issues. Five are fixed in code and
validated in-sandbox; the sixth (actually retraining XGBoost) needs a Windows run
because the sandbox can't load xgboost or reach the MLB API. Details below.

## What changed (all committed)

**New file `mlb_edge.py` — single source of truth** for probability adjustments,
conviction sizing, and dual-book logging. Both `mlb_daily.py` (automated path) and
`build_july1.py` (nightly-fallback template) now import it, so the calibration
lives in ONE place instead of being copy-pasted per day.

1. **Conviction recalibrated + favorite penalty** (`mlb_edge.conviction`).
   Week-1 data: underdogs 13-4 (+46% ROI), favorites 5-8 (−27% ROI); the biggest
   sizes (HIGH/MED-HIGH) were net losers while MEDIUM (+57%) carried the card.
   New rules: favorites are soft-capped (no HIGH-size favorite; max 0.5u; need a
   larger edge to bet at all), and the dog ladder's top is capped at 0.75u (down
   from 1.0u). Re-sizing week 1 with the same picks/results: **+2.78u → +3.53u
   (ROI 14.6% → 22.8%)**, and that's a lower bound (it excludes dropping the
   heavy-chalk favorites like MIL −169 / ATL −162 entirely).

2. **Overrides encoded as model adjustments** (`mlb_edge.blended_era`,
   `park_discount`). The manual fades I'd been doing by hand are now automatic:
   - recent-form weighting (blend last-5 ERA) — McLean 4.01 season → 4.74 modeled
   - FIP/xERA regression — E-Rod 2.21 ERA → 2.83 modeled
   - Coors/park-variance discount — edges at pf≥1.30 are halved (July-2 lesson)

3. **Dual-book logging** (`mlb_edge.log_picks`, wired into `build_july1.py`).
   Root cause of the "dashboard shows more picks than the record" confusion: the
   nightly workflow never auto-logged the model's picks — rows were inserted by
   hand, so only staked bets were recorded. Now every actionable model pick is
   written (result=NULL, `bet=0`) and graded next day. The picks you actually
   stake get `bet=1` (via `sync_bets.py` or the report). Compare the two books:
   `mlb_results.get_pick_record(bets_only=False)` = the MODEL; `bets_only=True` =
   what you bet. This is how we'll measure whether the discretionary overlay adds
   value. (2026-07-05's Arizona pick is flagged `bet=1`; full dual-book starts
   with the next run.)

4. **Line-570 syntax error** — already gone. `mlb_train.py` parses clean
   (py_compile + AST). The memory note was stale; no fix needed.

5. **CLV made honest** (`clv_report.py` + new `mlb_train.walk_forward_oos_probs`).
   It was grading the final model on its own training games (in-sample optimistic).
   Now it uses walk-forward out-of-sample predictions (train on prior seasons,
   predict the held-out season) and only falls back to in-sample with a loud
   warning when there's <2 seasons of data.

## What you need to run on Windows (sixth item — the actual retrain)

The trained XGBoost model still isn't active: the data tables (games/starters/odds)
were wiped by the July DB corruption, and the sandbox can't pull them or load
xgboost. On your Windows machine, where the MLB API and xgboost work:

```bat
cd C:\Users\bitsk\Claude\Projects\MLB Daily
python mlb_data.py --build --seasons 2018 2019 2020 2021 2022 2023 2024 2025 2026   REM repopulate games/starters/odds
python backfill_bullpen.py                                                          REM bullpen ERA (else constant 4.20)
python mlb_backfill.py --seasons 2018 2019 2020 2021 2022 2023 2024 2025 2026       REM streaks, day/night, OPS, def rank
python backfill_vs_sp_ops.py --seasons 2018 2019 2020 2021 2022 2023 2024 2025 2026 REM team OPS vs opposing SP handedness
python mlb_train.py                                          REM retrain; check "Active features" (want 34, not 24) + AUC (baseline 0.604)
python clv_report.py                                         REM now prints OUT-OF-SAMPLE ROI@close + AvgCLV
```

**DO NOT SKIP the two backfill steps.** `mlb_data.py --build` only fills the base
columns; bullpen ERA, streaks, day/night, OPS, and defensive rank come from the
backfill scripts. Skip them and `build_features` fills those 10 columns with
constant defaults → they're dropped as zero-variance → the model trains on 24
features instead of ~33 (still "works", but silently weaker). After training,
confirm the log says **~33 active features**, not 24.

**DB-path gotcha (fixed 2026-07-07):** the backfill scripts used to hardcode
`data/mlb.db` while the trainer reads the relocated live DB at
`%LOCALAPPDATA%\MLB-Daily\mlb.db`. Result: backfill wrote to a file the trainer
never opened, so retrains kept dropping the same 10 features. Both
`mlb_backfill.py` and `backfill_bullpen.py` now `from mlb_data import DB_PATH`, so
all three resolve the identical DB. If you ever see the trainer's PREFLIGHT path
differ from the backfill's `DB:` line, they're hitting different files again.

If `mlb_train.py` reports a good AUC (≈0.60+), the nightly run will pick up the
trained model automatically and stop using the ERA formula fallback. Until then
the formula fallback runs — but now with the recalibration and adjustments above.

## Files touched
- `mlb_edge.py` (new)
- `build_july1.py` (imports mlb_edge; blended ERA + park discount; dual-book logging) — `.bak` saved
- `mlb_daily.py` (conviction delegation + park discount) — `.bak` saved
- `mlb_train.py` (added `walk_forward_oos_probs`) — `.bak` saved
- `clv_report.py` (out-of-sample mode) — `.bak` saved

## Not done / deliberately left
- No change to the core `formula_prob` weights (0.028 ERA / 0.15 win%) — the
  calibration acts on sizing and inputs, which the 30-bet sample supports; tuning
  the formula coefficients needs more data.
- Constants in `mlb_edge.py` are week-1 calibrated on a TINY sample — re-derive
  them as the record grows. Don't treat them as precise.
