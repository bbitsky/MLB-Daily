# MLB Picks Report — Friday, July 3, 2026

*Generated: July 3, 2026 (automated nightly run) | Model: Formula fallback (ERA + win% differential) | Data: Web-researched (FanDuel Research, SportsGrid, OddsShark, ESPN — MLB Stats API / Odds API blocked in sandbox)*

> **Morning refresh (07:0x ET re-run):** July 2 grading re-verified against final box scores (both losses confirmed). Several previously-TBD starters are now confirmed — **Gerrit Cole** (NYY vs Twins), **Kyle Harrison** (MIL vs ARI), **Tyler Phillips** (MIA vs A's) — none of which creates a new value edge (all reinforce existing "pass" reads). The Cardinals line has ticked from +112 to **+106**; the play still clears the LEAN threshold. Numbers below updated to current market.

---

## Pipeline Status

The automated APIs (MLB Stats API, The Odds API) returned the expected sandbox proxy 403s, so this run used web-researched data for the slate, pitchers, and odds.

**Database recovery (again):** `data/mlb.db` was found corrupt on this run ("database disk image is malformed") — the recurring FUSE/lock issue. The picks table was recovered from `picks_history_backup.csv`, which was intact through July 1. Steps taken:

1. Graded July 2's two picks against final scores and appended them to `picks_history_backup.csv` (pre-edit backup saved as `picks_history_backup.pre-july2.csv`).
2. Rebuilt a clean database using the full production schema (games, starters, odds, picks, bullpen, umpires) with the `id` primary key that the P/L tracker requires — built in local storage and copied over the mount, since the FUSE mount blocks the in-place `unlink()` that `repair_mlb_db.py` needs. New DB passes `PRAGMA integrity_check` (**ok**) with all 27 graded picks and a working bankroll/pick-record feed.

The trained XGBoost model remains unavailable (`mlb_train.py` has an unclosed-paren syntax error at line 570); the ERA-differential + win% formula fallback was used, as on prior runs.

---

## July 2 Results & Audit — **0-2 (−1.00u)**

| Pick | Conviction | Final | Result | P/L |
|------|-----------|-------|--------|-----|
| Miami Marlins −126 @ COL | MED-HIGH (0.75u) | Rockies 14, Marlins 4 | ❌ LOSS | −0.75u |
| Philadelphia Phillies −122 vs PIT | LEAN (0.25u) | Pirates 6, Phillies 1 | ❌ LOSS | −0.25u |

A rough getaway day. Both sides had the better starter on paper and both got beaten decisively.

**Audit note — the Coors caveat was right, and still cost us.** The Marlins write-up explicitly flagged Coors Field variance (park factor 1.38, O/U 12.0) and held the size to 0.75u rather than a full unit. Colorado then hung 14 runs — exactly the high-variance blow-up the caveat described. Max Meyer's elite ERA edge (2.53 vs Freeland's 7.25) was fully neutralized by altitude. **Takeaway for the model:** at Coors, a starter ERA advantage should be discounted harder — arguably enough to drop most Coors favorites to LEAN or off the card entirely, not MED-HIGH. The Phillies loss (Rangel roughed up) was a low-conviction LEAN and is within normal noise.

**Running record: 16W-11L (59.3%) | +2.19u total.** (Down from +3.19u pre-July 2; discipline on sizing kept the damage to one unit on an 0-2 day.)

---

## July 3 Full Slate

Confirmed games with researched pitchers/odds. ERAs shown as researched; where an opposing starter was unconfirmed at generation time, the model was run neutral so it does not invent an edge.

| Away | Home | Away SP (ERA) | Home SP (ERA) | Away ML | Home ML | O/U |
|------|------|--------------|--------------|---------|---------|-----|
| **Cardinals** | Cubs | A. Pallante (3.83) | D. Peterson (5.86) | +106 | −128 | 8.5 |
| Pirates | **Nationals** | M. Keller (4.87) | F. Griffin (2.93) | +117 | −139 | 8.5 |
| Twins | **Yankees** | M. Paredes | G. Cole ✔ | +120 | −142 | 8.5 |
| Mets | **Braves** | TBD | B. Elder (~4.55) | +116 | −136 | 8.5 |
| Diamondbacks | **Brewers** | J. Cabrera (spot, 0-0) | K. Harrison ✔ | +140 | −167 | 8.5 |
| Athletics | **Marlins** | J. Perkins | T. Phillips ✔ | +120 | −142 | 9.0 |

*Other games (Orioles @ Reds, White Sox @ Guardians) were on the schedule but had no confirmed pitcher/odds pair at generation time and are not modeled.*

---

## Model Picks — Ranked by Edge

### 1. St. Louis Cardinals +106 @ Chicago Cubs — **LEAN (0.25u)** ⭐ Best value
**Edge: +3.6% | Model: STL 52.1%, Market: 48.5%**

The one clean value spot on the board. **Andre Pallante (9-5, 3.83 ERA)** draws **David Peterson (4-6, 5.86)** — a two-run ERA advantage — yet the market makes the Cubs a −128 home favorite. Pallante has allowed just 2 earned runs across his last 12.2 IP (two starts). Getting a plus-money price on the side with the better starter is the definition of a value dog.

⚠️ **Swing factor:** Wrigley Field wind. Live weather is unavailable in the sandbox — if a strong out-blowing wind is forecast, it favors the offenses and the total, muting the pitching edge. Confirm the forecast before first pitch. LEAN sizing reflects both the modest edge and the wind uncertainty.

**Bet: St. Louis Cardinals +106 (0.25u)**

---

## Right Side, No Value (informational — not a bet)

- **Nationals −139 vs Pirates:** Foster Griffin (8-2, 2.93 ERA, .210 opp AVG) is clearly the better arm over Mitch Keller (4.87), and the model likes Washington to win ~58.6%. But −139 already implies 58.2% — **the market has fully priced the mismatch.** Correct side, zero edge. Pass on the moneyline; the value here is confirming WSH as a strong parlay anchor if you're building elsewhere, not a standalone bet.

## Skip / Fade

- **Yankees −142 / Braves −136:** standard home chalk; opposing starters (NYY, and the Mets' arm) unconfirmed — no pitcher-driven read. Pass.
- **Brewers −167 vs Diamondbacks:** Arizona opens winless spot-starter Jose Cabrera at hitter-friendly American Family Field. Heavy chalk with no confirmed Brewers ERA to model — the "edge" on Arizona's +140 is a data artifact, not real. Pass.
- **Marlins −142 vs Athletics:** Miami's starter unconfirmed opposite Jack Perkins. No model play.

---

## Parlay Suggestion

**None today.** Only one pick clears the LEAN threshold, so there is no multi-leg spot. Discipline over volume.

---

## Summary Table

| Pick | ML | Conviction | Units | Edge |
|------|----|-----------|-------|------|
| St. Louis Cardinals | +106 | LEAN | 0.25u | +3.6% |
| **Total risk** | | | **0.25u** | |

*A deliberately small book: one modelable value edge, priced dogs elsewhere already efficient. The Nationals are the strongest team-side on the board but offer no betting value at −139.*

---

*Pitcher stats & odds: FanDuel Research, Bleacher Nation/DataSkrive, SportsGrid, OddsShark (2026 season), as of the automated morning run. Model: ERA-differential + win% formula fallback (trained XGBoost unavailable). Lines move — confirm before betting. Betting involves risk; only wager what you can afford to lose.*
