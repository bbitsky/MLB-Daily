# MLB Model Report — Monday, July 6, 2026

*Manual-research mode (MLB Stats API / Odds API blocked in sandbox). Model input:
numberFire per-game win probabilities from FanDuel Research; odds from FanDuel;
probable pitchers from FanDuel/FantasyPros. Sizing via the week-1-calibrated
`mlb_edge` ladder (favorites de-sized, top size capped at 0.75u).*

---

## Yesterday (7/5) result logged

- **Arizona Diamondbacks +104 (MED-HIGH, 0.5u) → LOSS (−0.5u).** Brewers beat the
  D-backs **3–2**; Jake Bauers homered off Eduardo Rodríguez in the 7th.
- Season model record after grading: **18W–13L (58.1%), +2.28u, bankroll ~$614.**

> Maintenance note: `data/mlb.db` was found malformed (mid-write corruption + stale
> WAL/journal) and was rebuilt from `picks_history_backup.csv` (integrity OK, 31
> picks restored). `run_daily.py` and `mlb_daily.py` were also truncated on the
> sandbox mount (FUSE sync lag) — `run_daily.py` was restored; `mlb_daily.py`
> hit its known stale line-570 error, so the manual `build_july6.py` path was used.

---

## Today's slate (8 games) — odds, pitchers, model probabilities

| Time (ET) | Matchup (Away @ Home) | Probable SPs (A / H) | Away ML | Home ML | Model (Away/Home) | Market edge |
|---|---|---|---|---|---|---|
| 2:10 | Phillies @ Royals | C. Sánchez (1.62) / N. Cameron | **−172** | +144 | 64.2% / 35.8% | +1.0% PHI (chalk) |
| 6:40 | Yankees @ Rays | C. Schlittler (1.50) / G. Jax | +100 | **−118** | 49.8% / 50.2% | none |
| 6:45 | Astros @ Nationals | M. Burrows (5.58) / M. Mikolas (5.44) | +116 | **−134** | 47.2% / 52.8% | +0.9% HOU |
| 7:15 | Mets @ Braves | F. Peralta (4.81) / R. López (3.31) | +110 | **−130** | 43.7% / 56.3% | none |
| 7:45 | Brewers @ Cardinals | S. Drohan / D. May | **−116** | −102 | 55.1% / 44.9% | +1.4% MIL |
| 9:40 | Diamondbacks @ Padres | B. Pfaadt / W. Buehler | −110 | **−106** | 43.0% / 57.0% | **+5.6% SD** (near-miss) |
| 9:45 | Blue Jays @ Giants | K. Gausman / L. Roupp (~3.80) | −110 | **−106** | 40.1% / 59.9% | **+8.4% SF ✅** |
| 10:10 | Rockies @ Dodgers | K. Freeland / E. Lauer | +150 | **−178** | 35.7% / 64.3% | none |

*Bold = market favorite. ERAs shown where reliably sourced for the 2026 sim season;
several starter ERAs conflicted across secondary sources and were left blank rather
than guessed. "Market edge" = model probability − vig-inclusive implied probability,
after park-variance discount (no high-variance park on tonight's card).*

---

## Value picks (ranked by edge)

### 1. San Francisco Giants −106 vs Blue Jays — **MEDIUM, 0.5u** — edge +8.4% ✅ *(only qualifying play)*

The board's single actionable edge. San Francisco is priced as a near-pick'em home
team (−106, 51.5% implied) but numberFire models the Giants at **59.9%** behind
Landen Roupp against Toronto's Kevin Gausman. Sized MEDIUM (0.5u) and **not** up:
the Giants are a weak team (37-52) and the edge leans almost entirely on the pitching
read, so it's a **monitor-for-late-lineup/scratch** spot before the 9:45 ET first
pitch. The week-1 audit (favorites 5-8, −27% ROI) is exactly why the ladder caps
favorites at 0.5u.

### Near-miss — Padres −106 vs Diamondbacks — edge +5.6% *(no bet)*

numberFire has San Diego at 57.0% at home (Buehler vs Pfaadt) against a near-pick'em
price. That +5.6% would be a LEAN on an underdog, but the recalibrated ladder requires
**≥6%** to back a **favorite**. Right side, fair number — pass, or a parlay anchor at
most.

### No plays — Phillies −172, Dodgers −178 (fair chalk), Yankees +100 (Schlittler priced in), Brewers −116, Mets/Braves, Rockies +150.

numberFire hugs the market on the rest of the slate; no side clears the edge
thresholds.

---

## Parlay suggestion

**None.** Only one play qualifies, so there's no 2+-leg alignment. Discipline over
volume — consistent with the July 5 single-play approach.

---

## Caveats

- **Model source:** numberFire win probabilities are used as the model input because
  the trained XGBoost needs live feature data (blocked in-sandbox) and the 2026-sim
  starter ERAs were inconsistent across secondary sources. numberFire hugs the market,
  so edges are naturally compressed — the ERA-differential formula (the project's
  original method, which favored underdogs +46% ROI in week 1) may surface value that
  a market-calibrated model won't, but reliable ERA inputs weren't available tonight.
- **Live odds/weather feeds unavailable** in this environment; lines may move before
  first pitch. Re-check the Giants line and both lineups before staking.
- Picks are **frozen** in `picks_frozen_2026-07-06.json`; the model book (Giants −106)
  is logged to the DB with `result=NULL` for tomorrow's grading.

---

### Sources
- [FanDuel Research — Monday's MLB Odds & Predictions, July 6](https://www.fanduel.com/research/mlb-betting-odds-07-6-2026)
- [FantasyPros — MLB Probable Pitchers](https://www.fantasypros.com/mlb/probable-pitchers.php)
- [ESPN — Brewers vs. Diamondbacks (Jul 5, 2026)](https://www.espn.com/mlb/game/_/gameId/401816042/brewers-diamondbacks)
- [NBC Sports — Bauers homers off Rodríguez, Brewers beat Diamondbacks 3-2](https://www.nbcsports.com/mlb/news/bauers-homers-off-rodriguez-in-7th-brewers-come-back-to-beat-diamondbacks-3-2)
