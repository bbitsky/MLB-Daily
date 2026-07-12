# MLB Model Report — Thursday, July 9, 2026

*Automated nightly run. **An independent model feed WAS reachable tonight** — the FanDuel Research July-9 page publishes **numberFire win probabilities** for every game, so tonight's edges are genuine (model probability minus market-implied), not the market-devig fallback used on July 8. Moneylines and probable starters are from the same board. Sizing runs through the week-1-calibrated `mlb_edge` ladder. The trained XGBoost model remains unavailable in the sandbox (disk-constrained), so numberFire is the probability source this run.*

## Bottom line

**5 qualifying plays, 2.25 units staked.** The headline is the **Chicago Cubs (+108) at Baltimore** — numberFire makes them a 61.4% favorite while the market has them a +108 road dog, a ~13-point disagreement and the day's only HIGH-conviction play. Two MEDIUM home-dog plays (Cardinals +108, Twins +114) and two LEANs (White Sox -112, Marlins +120) round out the card. Two games (Yankees @ Rays, Rockies @ Giants) carried no posted moneyline and are monitors only.

---

## Yesterday (July 8) — audit & results

**No action to grade.** July 8 was a disciplined no-play day: with no independent model feed reachable that night, every game was priced to its de-vigged fair line, nothing cleared the calibrated thresholds, and **0 units were staked**. There were no open positions to settle.

**Season record unchanged: 19W-13L (59.4%), +2.749u.** Bankroll $637.50. July 7 was also a no-play, so the last graded bet was July 6 (Giants -106, W).

**Audit / data-integrity note.** `data/mlb.db` was again found **malformed** on this run (the recurring sandbox/FUSE corruption — a fresh `mlb.db.corrupt-20260709_*` backup was auto-created). The documented recipe was applied: rebuilt a fresh schema in local (non-FUSE) storage, re-imported the pick history from `picks_history_backup.csv`, verified `PRAGMA integrity_check = ok` (record reconciles to 19W-13L, +2.749u), then copied the healthy file back over the mount. Likely root cause is SQLite writing directly to the FUSE mount mid-run; today's 5 picks were logged via a local-copy-then-copy-back path to avoid re-triggering it, and are now pending in the mount DB for tomorrow's grade. **Recommendation:** a Windows-side run (LocalAppData DB path) remains the durable fix.

---

## Today's slate — 13 games (numberFire model overlay)

Probabilities are numberFire's published win% (the model tonight); "Impl%" is the pick side's market-implied probability from the FanDuel line; "Edge" is model − implied through the `mlb_edge` park/vig adjustment. Pitchers listed away vs. home.

| Game (Away @ Home) | Starters (A/H) | Away ML / Home ML | numberFire | Call |
|---|---|---|---|---|
| **Cubs @ Orioles** | Peterson / Rogers | **+108** / -126 | Cubs 61.4% | ✅ **Cubs +108 — HIGH** |
| Red Sox @ **White Sox** | Sandoval / Kay | -104 / **-112** | White Sox 59.1% | ✅ White Sox -112 — LEAN |
| Brewers @ **Cardinals** | Henderson / Pallante | -126 / **+108** | Cardinals 53.6% | ✅ Cardinals +108 — MEDIUM |
| Guardians @ **Twins** | Williams / Ober | -134 / **+114** | Twins 51.5% | ✅ Twins +114 — MEDIUM |
| Mariners @ **Marlins** | Miller / Junk | -142 / **+120** | Marlins 47.7% | ✅ Marlins +120 — LEAN |
| Phillies @ Reds | Luzardo / Singer | -164 / +138 | Phillies 64.1% | Correct side, priced — pass |
| Braves @ Pirates | Elder / Keller | -118 / +100 | ~50/50 | Fair — pass |
| Royals @ Mets | Wacha / Manaea | +128 / -152 | Mets 59.9% | Market ≥ model — pass |
| Athletics @ Tigers | Perkins / Valdez | +118 / -138 | Tigers 55.2% | Market ≥ model — pass |
| D-backs @ Padres | Kelly / Canning | +108 / -126 | Padres 53.2% | Market ≥ model — pass |
| Angels @ Rangers | Detmers / Eovaldi | +120 / -142 | Rangers 56.8% | Market ≥ model — pass |
| Yankees @ Rays | Rasmussen / TBD | no line | Rays 62.2% | Monitor (no ML posted) |
| Rockies @ Giants | Feltner / TBD | no line | Giants fav | Monitor (no ML posted) |

---

## Value picks (ranked by edge)

1. **Chicago Cubs +108 @ Baltimore — HIGH, 0.75u.** Model 61.4% vs 48.1% implied → **+13.3% edge**. The market has Baltimore a -126 home favorite; numberFire makes Chicago the clearly stronger side. Road-favorite-priced-as-a-dog is exactly the spot the ladder sizes up. *To win 0.81u.*
2. **Chicago White Sox -112 vs Boston — LEAN, 0.25u.** Model 59.1% vs 52.8% implied → **+6.3% edge**. Clears the 6% favorite bar but only just; favorites are de-sized, hence LEAN. *To win 0.22u.*
3. **St. Louis Cardinals +108 vs Milwaukee — MEDIUM, 0.5u.** Model 53.6% vs 48.1% implied → **+5.5% edge**. Model fades the -126 Brewers and takes the home dog. *To win 0.54u.*
4. **Minnesota Twins +114 vs Cleveland — MEDIUM, 0.5u.** Model 51.5% vs 46.7% implied → **+4.7% edge**. Coin-flip game the market tilts to Cleveland; model takes the home dog price. *To win 0.57u.*
5. **Miami Marlins +120 vs Seattle — LEAN, 0.25u.** Model 47.7% vs 45.5% implied → **+2.2% edge**. Just clears the 2% underdog bar; smallest stake. *To win 0.30u.*

**Total staked: 2.25u** (potential +2.44u if all five win).

**Parlay:** No auto-parlay generated — the discipline rule wants 2+ HIGH/MED-HIGH legs and tonight has a single HIGH (Cubs) plus two MEDIUMs. *Optional flier only:* a 2-leg of the two independent-edge underdogs, **Cubs +108 & Cardinals +108** (≈ +332 combined), if you want correlated model-vs-market exposure — but it sits below the calibrated parlay threshold, so it is not a recommended play.

---

## Data & environment notes

- **Model feed available:** numberFire per-game win probabilities were published on the FanDuel Research July-9 page and used directly as the model probability — a real independent overlay, unlike July 8's market-devig pass.
- **Two unposted lines:** Yankees @ Rays (Rasmussen vs. a TBD Rays arm) and Rockies @ Giants (SF starter unlisted) had no moneyline on the board at pull time and were left off the actionable slate rather than priced on a guess. numberFire liked the Rays (62.2%) and Giants in those.
- **ERAs unavailable:** 2026-sim per-pitcher ERAs were not reliably paired across sources, so the dashboard shows a neutral 4.15 placeholder (display only — picks are driven by the numberFire probability, not ERA).
- **Sandbox limits:** MLB Stats/Odds APIs 403; XGBoost and pybaseball unavailable (disk-constrained), so the trained model runs on formula fallback. `mlb_metrics.json` is currently corrupt (backtest panel falls back to the ERA path); non-blocking, flagged for the next Windows-side rebuild.
- **No altitude game:** Colorado plays at Oracle Park, not Coors — no park-variance discount triggered. Live weather APIs remain blocked; O/U totals shown are park-based estimates.

*Sources: [FanDuel Research — MLB odds July 9, 2026](https://www.fanduel.com/research/mlb-betting-odds-07-9-2026) (moneylines, probable starters, numberFire win probabilities).*
