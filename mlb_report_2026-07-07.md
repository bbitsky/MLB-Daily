# MLB Model Report — Tuesday, July 7, 2026

*Automated nightly run. Model on formula fallback (XGBoost lib unavailable in sandbox); win probabilities sourced from FanDuel Research per game and sized with the week-1-calibrated `mlb_edge` ladder.*

## Bottom line

**No qualifying play tonight.** Across the 7 modeled games, no side clears the calibrated threshold (favorites need ≥6% edge, underdogs ≥2%). The best number on the board — Cubs -112 (+4.4%) — is a favorite short of the 6% bar, so it's a monitor, not a bet. **0 units staked.** This is a disciplined pass, consistent with the week-1 audit that de-sized favorites (they went 5-8, -27% ROI).

---

## Yesterday (July 6) — result logged

| Pick | Odds | Conv | Stake | Result | P/L |
|---|---|---|---|---|---|
| San Francisco Giants ML | -106 | MEDIUM | 0.5u | **WIN** (SF 10-1 vs Toronto) | **+0.47u** |

The Giants were the only qualifying play on July 6 (+8.4% model edge behind Landen Roupp). Roupp threw 8 innings, 3 hits; Heliot Ramos drove in 5. Clean win.

**Season record after 07-06: 19W-13L, +2.749u.**

*(DB note: `data/mlb.db` was found malformed again on this run — a recurring sandbox/FUSE issue. Rebuilt from `picks_history_backup.csv` via the documented recipe: schema+picks rebuilt in local storage, integrity verified, copied back over the mount, stale journal truncated. All 32 graded picks intact.)*

---

## Today's slate (7 games modeled) — ranked by model edge

| Game | Starters (ERA) | ML | Model prob | Mkt implied | Edge | Call |
|---|---|---|---|---|---|---|
| **Cubs @ Orioles** | Boyd 5.08 / Baz 4.19 | CHC -112 | CHC 57.2% | 52.8% | **+4.4%** | NEAR-MISS (fav <6%) |
| Pirates vs Braves | Waldrep 3.68 / Skenes 3.62 | PIT -180 | PIT 65.4% | 64.3% | +1.1% | Fair — pass |
| Brewers @ Cardinals | Misiorowski / Pallante 3.60 | MIL -140 | MIL 58.8% | 58.3% | +0.5% | Fair — pass |
| D-backs @ Padres | Gallen / Bergert | SD -124 | SD 55.5% | 55.4% | +0.1% | Fair — pass |
| Blue Jays @ Giants | Gausman 4.19 / Roupp 3.80 | TOR -117 | TOR 54.0% | 53.9% | +0.1% | Pick'em — pass |
| Athletics @ Tigers | Springs / Olson | DET -110 | DET 51.0% | 52.4% | -1.4% | Pick'em — pass |
| Rockies @ Dodgers | Lorenzen / Wrobleski | LAD -266 | LAD 72.0% | 72.7% | -0.7% | Chalk — pass |

*Model prob = FanDuel Research win probability where independently available (Cubs, Pirates, Brewers); market-devigged elsewhere (zero edge by construction). Park factors applied to the edge before sizing.*

## Why no bet

- **Cubs -112 (+4.4%)** is the lone positive-edge favorite of any size, but the recalibrated ladder requires **≥6%** to back a favorite — favorites went 5-8 (-27% ROI) in week 1, and the two worst bets of the season were heavy chalk. Correct pass; parlay anchor at most.
- **Pirates -180 / Dodgers -266 / Brewers -140** are all correctly priced heavy or moderate favorites — the model agrees with the market inside a point.
- **No underdog** reaches even the +2% LEAN threshold; the biggest dog edges are negative (Cardinals +118 at -4.7%, D-backs +105 at -4.3%).
- **Blue Jays/Giants** is a rematch of last night's 10-1 SF blowout, but the market fully corrected — now a coin flip at -117/-103.

**Parlay:** none. One near-miss and no qualifying legs — discipline over volume.

---

## Data & environment notes

- MLB Stats API / Odds API returned proxy 403 (expected in sandbox); the Chrome browser tool was offline, so the FanDuel daily odds grid could not be pulled in one shot. Odds, probable starters and model win probabilities were assembled **game-by-game** from FanDuel Research and public books.
- Public schedule/score pages (ESPN, Covers) were serving **stale caches** (July 3-4), so only forward-looking FanDuel preview pages were usable for July 7.
- Four East-coast games (Reds @ Yankees, Mets @ Phillies, Red Sox @ Mariners, Nationals @ Rays) could not be reliably sourced and were **left off** the slate rather than guessed. None would have changed the no-play conclusion.
- Model remains on ERA/win% formula fallback (XGBoost unavailable in sandbox); a Windows-side data pull + retrain is still required to activate the trained model.

*Dashboard: `mlb_dashboard_2026-07-07.html` → pushed to https://bbitsky.github.io/MLB-Daily/*
