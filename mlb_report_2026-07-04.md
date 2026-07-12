# MLB Picks Report — Saturday, July 4, 2026

*Generated: July 4, 2026 (automated nightly run) | Model: Formula fallback (ERA + win% differential) | Data: Web-researched (FanDuel Research primary source — MLB Stats API / Odds API blocked in sandbox)*

---

## Pipeline Status

The automated APIs (MLB Stats API, The Odds API) returned the expected sandbox proxy 403s, so this run used web-researched data (FanDuel Research per-game pages) for the slate, pitchers, and odds.

**Database:** `data/mlb.db` passed `PRAGMA integrity_check` (**ok**) on this run — no corruption this time. July 3's pick was graded manually (score API blocked) and appended; `picks_history_backup.csv` was brought current through July 3 (it had lagged at June 30). The trained XGBoost model remains unavailable (unresolved dependency/space constraints in sandbox); the ERA-differential + win% formula fallback was used, as on prior runs.

**Disk note:** the sandbox filesystem hit 100% mid-run; cleared ~700 MB of temp to proceed. `scikit-learn`/`xgboost` could not be installed (no space), but `run_daily.py` does not require them.

---

## July 3 Results & Audit — **1-0 (+0.27u)** ✅

| Pick | Conviction | Final | Result | P/L |
|------|-----------|-------|--------|-----|
| St. Louis Cardinals +106 @ CHC | LEAN (0.25u) | **Cardinals 17, Cubs 1** | ✅ WIN | +0.27u |

**Audit note — the value-dog thesis paid off, emphatically.** The one pick on July 3's deliberately small card was the plus-money side with the clear starting-pitcher ERA edge (Pallante 3.83 over Peterson 5.86), taken at +106 despite the Cubs being −128 home favorites. St. Louis won 17-1 — a 17-hit blowout with three-run homers from Nathan Church and Masyn Winn. The Wrigley-wind caveat flagged at generation did not bite.

**Takeaway for the model:** this reinforces the same edge the July 1 slate exploited — a real ERA advantage on the *plus-money* side is the model's most reliable signal, and the discipline of betting one clean edge rather than forcing volume continues to be correct. No process change indicated; the read worked as designed.

**Running record: 17W-11L (60.7%) | +2.46u total | Bankroll $623.** (Up from +2.19u / $609.50 after the July 3 win.)

---

## July 4 Full Slate — Researched Games

Confirmed pitchers/odds from FanDuel Research per-game pages. Where a starter is just off the IL (0-0 record, small-sample ERA), the ERA edge is discounted for uncertainty rather than taken at face value.

| Away | Home | Away SP (ERA) | Home SP (ERA) | Away ML | Home ML | O/U |
|------|------|--------------|--------------|---------|---------|-----|
| **Pirates** | Nationals | B. Ashcraft (3.33) | Z. Littell (5.29) | −164 | +138 | 9.5 |
| **Tigers** | Rangers | J. Flaherty (4.97) | K. Rocker (3.83) | −116 | −102 | 8.0 |
| Orioles | **Reds** | B. Young (3.11) | H. Greene (0-0, off IL) | +104 | −122 | 9.5 |
| Blue Jays | **Mariners** | S. Bieber (0-0, off IL, 6.00) | L. Gilbert (3.42) | −134 | +114 | 7.0 |
| White Sox | **Guardians** | S. Burke (3.69) | P. Messick (2.85) | +120 | −142 | 7.5 |
| Cardinals | **Cubs** | M. Mikolas (4-5) | C. Rea (5-3) | +120 | −142 | 9.5 |
| Mets | **Braves** | S. Manaea | C. Sale | −102 | −116 | ~8.5 |
| Padres | **Dodgers** | G. Canning | Y. Yamamoto | +132 | −160 | 8.5 |

*Other games on the July 4 board (Twins @ Yankees, Rays @ Astros, Giants @ Rockies, Phillies @ Royals, Red Sox @ Angels, Marlins @ Athletics, Brewers @ Diamondbacks) did not have a confirmed pitcher/ERA + current-odds pair retrievable at generation time and are not modeled — the model runs neutral rather than inventing an edge.*

---

## Model Picks — Ranked by Edge

### 1. Seattle Mariners +114 vs Toronto Blue Jays — **MED-HIGH (0.5u)** ⭐ Best value
**Edge: ~+8% | Model: SEA ~55%, Market implied: 46.7% | (FanDuel's own model: SEA 69.1%)**

The clearest market/model gap on the board. **Logan Gilbert (6-5, 3.42 ERA)** is a legitimate front-line arm pitching **at home**, yet Seattle is priced as a **+114 underdog** because Toronto sends **Shane Bieber**, a marquee name — but Bieber is **just off the IL (0-0, 6.00 ERA, tiny sample)**. The market is paying for the reputation; the model is paying for the performance. FanDuel's own projection has Seattle at 69.1% — a ~22-point disagreement with the price it's offering. Even discounting that hard for the two-way returning-pitcher variance (Bieber could dominate on any given night), a fair line here is Seattle pick'em-to-favored, not +114. Getting the better, healthier starter at home at plus money is the definition of value.

⚠️ **Swing factor:** Bieber's form is a genuine unknown — a vintage Bieber outing flips this. That two-way uncertainty is why the size is 0.5u (MED-HIGH), not a full unit.

**Bet: Seattle Mariners +114 (0.5u)**

### 2. Texas Rangers −102 vs Detroit Tigers — **LEAN (0.25u)**
**Edge: ~+3% | Model: TEX ~52.5%, Market implied: 50.5% | (FanDuel's model: TEX 51.7%)**

**Kumar Rocker (2-6, 3.83 ERA)** has better run-prevention than **Jack Flaherty (1-8, 4.97 ERA)** — a ~1.1-run ERA edge — and Texas is **at home**, yet the line is essentially a pick'em (Texas actually the −102 "dog" to Detroit's −116). Records are misleading here; Rocker has pitched better than his W-L, and Flaherty's 1-8 reflects a rough season. Small, clean edge on the better home arm at near-even money.

**Bet: Texas Rangers −102 (0.25u)**

---

## Right Side, No Value (informational — not a bet)

- **Cleveland Guardians −142 vs White Sox:** Parker Messick (7-5, 2.85) is the better arm over Sean Burke (3.69) and Cleveland is the correct side, but −142 already implies ~58.7% and the model lands there too. Fair price, minimal edge. Strong **parlay anchor**, not a standalone bet.
- **Pirates −164 @ Nationals:** Braxton Ashcraft (8-3, 3.33) clearly outclasses Zack Littell (5.29), but −164 (implied 62.1%) fully prices the mismatch (FanDuel model: PIT 62.2%). Correct side, zero edge. Pass.

## Skip / Fade

- **Reds −122 vs Orioles:** Hunter Greene is elite talent but is **0-0 off the IL** — too much uncertainty to back at −122 against a steady Brandon Young (3.11). Pass.
- **Cubs −142 vs Cardinals:** home chalk after last night's 17-1 loss; Rea/Mikolas is roughly a wash on the arms and there's no plus-money value on the correct side. Pass.
- **Braves −116 vs Mets:** Sale over Manaea leans Atlanta, but it's a pick'em price with no real edge. Pass.
- **Dodgers −160 vs Padres:** Yamamoto over Canning is priced correctly on heavy chalk. No value. Pass.

---

## Parlay Suggestion

**Optional 2-leg (small, 0.25u):** **Mariners +114 & Rangers −102** — both are model-edge sides where we're getting the better home starter at pick'em-or-better prices. Combined ≈ **+324**. This is a lottery-flavored add on the two edges we actually like, not a core play. Discipline still favors the straight Mariners bet as the main position.

---

## Summary Table

| Pick | ML | Conviction | Units | Edge |
|------|----|-----------|-------|------|
| Seattle Mariners | +114 | MED-HIGH | 0.5u | ~+8% |
| Texas Rangers | −102 | LEAN | 0.25u | ~+3% |
| *(opt.) Mariners + Rangers parlay* | +324 | LOTTERY | 0.25u | — |
| **Total core risk** | | | **0.75u** | |

*Two modelable edges, both on the better home starter at a soft price; priced favorites elsewhere already efficient. The Mariners are the standout — the market is paying for Bieber's name over Gilbert's form.*

---

*Pitcher stats & odds: FanDuel Research per-game pages (July 4, 2026). Model: ERA-differential + win% formula fallback (trained XGBoost unavailable). Lines move — confirm before betting. Betting involves risk; only wager what you can afford to lose.*
