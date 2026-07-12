# MLB Picks Report — Sunday, July 5, 2026

*Generated: July 5, 2026 (automated nightly run) | Model: ERA-differential + win% formula fallback (trained XGBoost unavailable in sandbox) | Data: web-researched (FanDuel Research / numberFire, FantasyPros, Bleacher Nation, SportsGrid — MLB Stats API / Odds API blocked in sandbox)*

---

## Pipeline Status

The automated APIs (MLB Stats API, The Odds API) returned the expected sandbox proxy 403s, so this run used web-researched data (FanDuel Research per-game pages, FantasyPros probables, SportsGrid) for the slate, pitchers, and odds.

**Database recovery (recurring FUSE/WAL issue — now hardened):** `data/mlb.db` was found **malformed** with a stale `mlb.db-wal` present (the recurring lock/FUSE-sync corruption). Recovery steps taken:

1. The picks table could not be read even page-by-page, so the DB was rebuilt from `picks_history_backup.csv` off-mount and copied back over the FUSE mount (the in-place `unlink()` that `repair_mlb_db.py` needs is blocked by the mount).
2. **Root-cause mitigation:** the rebuilt DB was switched from **WAL to DELETE journal mode**, which should prevent the stale-`-wal` corruption that has recurred on this sandbox. Stale `-wal`/`-shm` files were truncated to zero.
3. **Grading gap found and fixed:** the CSV backup had the **July 3 Cardinals pick still ungraded** — last night's grade was lost to the corruption before it persisted. It was regraded (WIN) and July 4's picks were graded and appended (details below).

The trained XGBoost model remains unavailable (`libxgboost.so` fails to load — no OpenMP runtime + no disk to reinstall in sandbox); the ERA-differential + win% formula fallback was used, as on prior runs. Disk was cleared (~0.5 GB) to proceed.

---

## July 3 Results & Audit (regraded) — **1-0 (+0.27u)** ✅

The July 3 grade was re-applied after last night's corruption dropped it before it saved.

| Pick | Conviction | Final | Result | P/L |
|------|-----------|-------|--------|-----|
| St. Louis Cardinals +106 @ CHC | LEAN (0.25u) | Cardinals 17, Cubs 1 | ✅ WIN | +0.27u |

---

## July 4 Results & Audit — **1-1 (+0.32u)**

| Pick | Conviction | Final | Result | P/L |
|------|-----------|-------|--------|-----|
| Seattle Mariners +114 vs TOR | MED-HIGH (0.5u) | **Mariners 11, Blue Jays 0** | ✅ WIN | +0.57u |
| Texas Rangers −102 vs DET | LEAN (0.25u) | Tigers 3, Rangers 0 | ❌ LOSS | −0.25u |
| *(opt.) Mariners + Rangers parlay +324* | LOTTERY (0.25u) | Rangers leg lost | ❌ LOSS | *(info only)* |

**Audit note — the marquee-name fade paid off exactly as designed; the pick'em lean was pure variance.** The core thesis on July 4 was that the market was paying for *reputation over form*: **Logan Gilbert (3.42 ERA, healthy, at home) as a +114 dog** to **Shane Bieber, just off the IL**. Gilbert then took a **one-hitter into the 8th** in an **11-0 rout** (Arozarena grand slam, Raleigh three-run HR) — the healthier, better-form starter at plus money delivered. This is the model's single most reliable signal reinforced yet again: *a real edge on the plus-money side.*

The Rangers −102 LEAN was the opposite kind of bet — a near-pick'em on a thin (~1-run) ERA edge (Rocker over Flaherty on paper) with no plus-money cushion. **Jack Flaherty flipped the script and threw a shutout (Tigers 3-0).** No process error: it was correctly sized as a 0.25u LEAN precisely because the edge was small and record-based rather than form-based. **Takeaway:** keep concentrating units on the plus-money form edges (Gilbert-type) and keep the near-pick'em ERA leans small or off the card — the win/loss split on July 4 is exactly the sizing logic working.

**Running record: 18W-12L (60.0%) | +2.78u total | Bankroll $639.** (Up from +2.46u / $623 after grading July 3–4.)

---

## July 5 Full Slate — "Star-Spangled Sunday" (all 15 games)

Confirmed pitchers/odds from FanDuel Research / FantasyPros. Games without a confirmed pitcher-ERA + current-odds pair at generation time are listed but not modeled (the model runs neutral rather than inventing an edge).

| Away | Home | Away SP (ERA) | Home SP (ERA) | Away ML | Home ML | O/U |
|------|------|--------------|--------------|---------|---------|-----|
| Mets | **Braves** | N. McLean (4.01*) | M. Perez (3.27) | +154 | −184 | 8.0 |
| Pirates | **Nationals** | B. Chandler (4.62) | C. Cavalli (3.69) | +116 | −134 | 9.0 |
| Twins | **Yankees** | J. Ryan (3.61) | R. Weathers (4.08) | +116 | −136 | 8.5 |
| Marlins | **Athletics** | E. Pérez (4.21) | G. Jump (2.93) | +103 | −123 | 8.0 |
| Brewers | **Diamondbacks** | B. Sproat (5.28) | E. Rodriguez (2.21) | −124 | **+104** | 8.5 |
| Cardinals | **Cubs** | M. Liberatore (5.33) | J. Assad (4.53) | +135 | −155 | 8.5 |
| Giants | **Rockies** | T. Mahle (5.67) | T. Gordon | −124 | +107 | 13.0 |
| Orioles | Reds | — | — | — | — | — |
| White Sox | Guardians | — | — | — | — | — |
| Phillies | Royals | — | — | — | — | — |
| Rays | Astros | — | — | — | — | — |
| Tigers | Rangers | — | — | — | — | — |
| Blue Jays | Mariners | — | — | — | — | — |
| Padres | Dodgers | — | — | — | — | — |
| Red Sox | Angels | — | — | — | — | — |

*\*McLean's 4.01 season ERA is misleading — see below.*

---

## Model Picks — Ranked by Edge

### 1. Arizona Diamondbacks +104 vs Milwaukee Brewers — **MED-HIGH (0.5u)** ⭐ Best value
**Edge: ~+7.4% | Model: ARI ~56.5%, Market implied: 49.0%**

The board's one clean plus-money edge, and it's the model's favorite type of spot. Arizona sends **Eduardo Rodriguez (7-2, 2.21 ERA, just named an All-Star)** at home, yet is priced as a **+104 underdog** — because Milwaukee is an elite *team* (MLB-best 3.35 staff ERA). But tonight Milwaukee doesn't throw its staff average; it throws **Brandon Sproat (3-4, 5.28 ERA)**. On the actual pitching matchup, Arizona has a ~3-run starter ERA advantage *and* home field, and you're getting it at **plus money**. That is the exact signal that hit on July 1, July 3, and July 4 (Gilbert).

⚠️ **Why 0.5u and not a full unit — two honest caveats:** (1) **numberFire disagrees**, leaning Milwaukee on overall team strength — a genuine counter-signal (on July 4 their model *agreed* with our Gilbert play; here it doesn't). (2) **E-Rod's 3.98 FIP** sits well above his 2.21 ERA, hinting at some regression. Both are priced into the reduced size, not ignored.

**Bet: Arizona Diamondbacks +104 (0.5u)**

---

## Right Side, No Value (informational — not a bet)

- **Athletics −123 vs Marlins:** Gage Jump (2.93) is the better arm over Eury Pérez (4.21) and the A's are home, but −123 (55.2% implied) already prices the model's ~55% read. Correct side, fair number — a **parlay anchor** at most, not a standalone bet.
- **Cubs −155 vs Cardinals:** Chicago has the better arm (Assad 4.53 vs Liberatore 5.33) *and* the majors' best offense vs LHP against a lefty. Correct side, but no plus-money value on the Cardinals dog. Pass.

## Skip / Fade

- **Braves −184 vs Mets — the trap on the board.** Both numberFire (ATL 50%) and our formula (~55%) call −184 too heavy, so **Mets +154 screens as value**. We **pass anyway**: **Nolan McLean's 4.01 season ERA hides a 6.92 ERA / 5.49 FIP since May** — his recent form has collapsed. The form red flag voids the paper edge. Monitor only.
- **Pirates +116 @ Nationals — no clean read.** numberFire likes the Pirates dog (58.5%); our ERA formula likes Cavalli (3.69) over Chandler (4.62) for Washington, and −134 already prices WSH fairly. Conflicting signals cancel. Pass.
- **Giants/Rockies at Coors (O/U 13.0) — skip per the July 2 audit lesson.** Discount starter ERA edges hard at altitude; Mahle (5.67) is poor regardless. The formula's +3.7% "lean" on the Rockies is a Coors artifact. No play.
- **Twins +116 @ Yankees:** Joe Ryan (3.61) is modestly better than Weathers (4.08), but the Yankees' team/home strength offsets the ~0.5-run edge to roughly fair. No play.

---

## Parlay Suggestion

**None.** Only one pick clears the value threshold today. Consistent with the record's core lesson (July 4's split, July 2's loss), discipline favors the single straight Arizona position over manufacturing a multi-leg. If pairing, the A's −123 is the only reasonable favorite anchor — but it carries no edge of its own.

---

## Summary Table

| Pick | ML | Conviction | Units | Edge |
|------|----|-----------|-------|------|
| Arizona Diamondbacks | +104 | MED-HIGH | 0.5u | ~+7.4% |
| **Total core risk** | | | **0.5u** | |

*One clean, plus-money, better-starter-at-home edge (E-Rod). Everything else is either correctly priced chalk, a Coors variance trap, or a form-collapse mirage (Mets). The market is paying for Milwaukee's roster over Arizona's arm — the model takes the arm.*

---

*Pitcher stats & odds: FanDuel Research / numberFire, FantasyPros, SportsGrid (July 5, 2026). Model: ERA-differential + win% formula fallback (trained XGBoost unavailable). Lines move — confirm before betting. Betting involves risk; only wager what you can afford to lose.*


---

## Why / Why-Not Bet — 2026-07-05

**No qualifying edge today.** Nothing clears the value threshold; the disciplined play is no bet.

**Everything else got filtered out:**

- **New York Mets @ Atlanta Braves** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Nolan McLean (3.81) vs Martín Pérez (3.54)]
- **Miami Marlins @ Athletics** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Eury Pérez (4.21) vs Gage Jump (2.93)]
- **St. Louis Cardinals @ Chicago Cubs** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Matthew Liberatore (5.42) vs Javier Assad (4.28)]
- **Philadelphia Phillies @ Kansas City Royals** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Aaron Nola (6.17) vs Luinder Avila (5.25)]
- **San Francisco Giants @ Colorado Rockies** (PARK) — Park-variance discount (Coors Field, PF 1.38): starter-ERA edges are unreliable here (July-2 Coors lesson). Skip. [Tyler Mahle (5.67) vs Tanner Gordon (6.69)]
- **Boston Red Sox @ Los Angeles Angels** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Ranger Suarez (2.94) vs Ryan Johnson (7.40)]
- **Milwaukee Brewers @ Arizona Diamondbacks** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Brandon Sproat (5.28) vs Eduardo Rodriguez (2.21)]
- **San Diego Padres @ Los Angeles Dodgers** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [JP Sears (6.97) vs Emmet Sheehan (5.08)]
- **Chicago White Sox @ Cleveland Guardians** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Chris Murphy (3.79) vs Tanner Bibee (3.69)]
- **Toronto Blue Jays @ Seattle Mariners** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Trey Yesavage (3.34) vs Emerson Hancock (3.47)]
- **Tampa Bay Rays @ Houston Astros** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Mason Englert (3.96) vs Peter Lambert (3.51)]
- **Baltimore Orioles @ Cincinnati Reds** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Kyle Bradish (3.75) vs Nick Lodolo (4.68)]
- **Minnesota Twins @ New York Yankees** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Joe Ryan (3.43) vs Ryan Weathers (4.29)]
- **Detroit Tigers @ Texas Rangers** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Casey Mize (2.63) vs Kumar Rocker (3.83)]
- **Pittsburgh Pirates @ Washington Nationals** (FLAG) — Away starter short rest (1d) -> -3% — the form/matchup flag voids the paper edge. Monitor, no bet. [Bubba Chandler (4.82) vs Cade Cavalli (3.88)]

**Parlay:** 8 qualifying combo(s) — see parlay section.

**Caveats:** Model: ERA-differential + win% formula fallback (trained XGBoost unavailable). Lines move — confirm the price is still live before staking.


---

## Why / Why-Not Bet — 2026-07-05

**Diamondbacks +104 vs Brewers — MED-HIGH (0.5u)**  ·  model 56.5% vs 49.0% implied · edge +7.4%

Eduardo Rodriguez (2.21 ERA/3.20 modeled) is the far better arm at home vs Sproat (5.28); Getting the superior starter at +104 plus money — the model's most reliable signal. Sized down — numberFire leans Milwaukee on team strength; E-Rod 3.98 FIP hints at some regression — sized 0.5u not full.

**Everything else got filtered out:**

- **Giants @ Rockies** (PARK) — Park-variance discount (Coors Field, PF 1.38): starter-ERA edges are unreliable here (July-2 Coors lesson). Skip. [T. Mahle (5.67) vs T. Gordon (5.50)]
- **Cardinals @ Cubs** (FAIR) — Model ~44% vs +135 implied 43% — roughly fair. No edge, pass. [M. Liberatore (5.33) vs J. Assad (4.53)]
- **Twins @ Yankees** (FAIR) — Model ~47% vs +116 implied 46% — roughly fair. No edge, pass. [J. Ryan (3.61) vs R. Weathers (4.08)]
- **Marlins @ Athletics** (CHALK) — Correct side (Athletics -123) but the price already prices the ~56% read. Parlay anchor at most, not a standalone bet. [E. Perez (4.21) vs G. Jump (2.93)]
- **Mets @ Braves** (FLAG) — McLean 4.01 season ERA hides 6.92/5.49 FIP since May — form collapse — the form/matchup flag voids the paper edge. Monitor, no bet. [N. McLean (5.00) vs M. Perez (3.27)]
- **Pirates @ Nationals** (PASS) — Conflicting or absent edge — no clean read. Pass. [B. Chandler (4.62) vs C. Cavalli (3.69)]

**Parlay:** None — one edge (or none), discipline favors the single straight over manufacturing a multi-leg.

**Caveats:** Model: ERA-differential + win% formula fallback (trained XGBoost unavailable). Lines move — confirm the price is still live before staking.
