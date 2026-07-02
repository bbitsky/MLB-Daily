# MLB Picks Report — Thursday, July 2, 2026

*Generated: July 2, 2026 (automated nightly run) | Model: Formula fallback (ERA + win% differential) | Data: Web-researched (MLB Stats API / Odds API blocked in sandbox)*

---

## Pipeline Status

Automated APIs (MLB Stats API, The Odds API) returned the expected sandbox proxy errors, so this run used web-researched data (FanDuel Research, Baseball-Reference) for the slate, pitchers, and odds.

**Database recovery:** `data/mlb.db` was found corrupt again this run ("database disk image is malformed" across `mlb.db`, `mlb.db.bak`, and both `mlb_repaired.db` copies). The **picks table itself was intact** and matched `picks_history_backup.csv` through June 30 — July 1's picks had never been logged before the corruption. Recovery steps taken:

1. Recovered July 1's five picks from `mlb_report_2026-07-01.md`, graded them against final scores, and appended them to `picks_history_backup.csv` (backup saved as `picks_history_backup.pre-july1.csv`).
2. Rebuilt a clean database from the CSV. The normal `repair_mlb_db.py` failed because the FUSE mount blocks file deletion, so the DB was rebuilt in local storage and copied over the existing file. New DB passes `PRAGMA integrity_check` (**ok**) with all 25 picks restored.
3. Also repaired a truncated `run_daily.py` (a mount sync artifact had cut it off mid-line 44).

---

## June 30 → July 1 Audit

### July 1 Results — **5-0 straight (+3.46u)** 🔥

| Pick | Conviction | Final | Result | P/L |
|------|-----------|-------|--------|-----|
| SF Giants +100 vs ARI | HIGH (1.0u) | SF 6, ARI 4 | ✅ WIN | +1.00u |
| OAK Athletics +138 vs LAD | MEDIUM (0.5u) | OAK 7, LAD 1 | ✅ WIN | +0.69u |
| WSH Nationals +160 @ BOS | MEDIUM (0.5u) | WSN 10, BOS 2 | ✅ WIN | +0.80u |
| DET Tigers +120 @ NYY | MEDIUM (0.5u) | DET 6, NYY 2 | ✅ WIN | +0.60u |
| PHI Phillies -136 vs PIT | MEDIUM (0.5u) | PHI 10, PIT 6 | ✅ WIN | +0.37u |

A clean sweep — every value dog (SF, OAK, WSN, DET) landed, plus the Wheeler-backed Phillies favorite. The optional SF+DET parlay (~+320) also would have cashed.

**Running session: 16W-9L (64.0%) | +3.19u total | Bankroll: $659.70**

---

## July 2 Full Slate

Thursday is a light **getaway-day card** (mostly early-afternoon starts). Confirmed games:

| Away | Home | Away SP (ERA) | Home SP (ERA) | Away ML | Home ML | O/U |
|------|------|--------------|--------------|---------|---------|-----|
| Pirates | **Phillies** | J. Jones (5.76) | A. Rangel (4.50) | +104 | -122 | 9.5 |
| Reds | **Brewers** | A. Abbott (3.88) | S. Drohan (3.12) | +136 | -162 | 9.0 |
| **Marlins** | Rockies | M. Meyer (2.53) | K. Freeland (7.25) | -126 | +108 | 12.0 |
| **Rays** | Royals | TBD | TBD | -118 | +100 | 10.5 |

---

## Model Picks — Ranked by Edge

### 1. Miami Marlins -126 @ Colorado Rockies — **MED-HIGH (0.75u)**
**Edge: +6.4% | Model: MIA 62.2%, Market: 55.8%**

The clearest talent gap on the board. **Max Meyer is 9-0 with a 2.53 ERA (112 K)** — among NL ERA leaders — against **Kyle Freeland (1-7, 7.25 ERA)**, one of the worst qualified marks in baseball. The market only prices Miami at -126.

⚠️ **Coors caveat:** Chase — this is Coors Field (park factor 1.38, O/U 12.0). Altitude compresses pitching edges and inflates variance, so the moneyline is preferable to the run line and the sizing is held at 0.75u rather than a full HIGH unit.

**Bet: Miami Marlins -126 (0.75u)**

---

### 2. Philadelphia Phillies -122 vs Pittsburgh Pirates — **LEAN (0.25u)**
**Edge: +3.4% | Model: PHI 58.3%, Market: 54.9%**

Alan Rangel (4.50) over Jared Jones (5.76), with the Harper/Schwarber core at Citizens Bank Park. FanDuel's own model agrees (PHI 55.2%). A modest edge — LEAN only.

**Bet: Philadelphia Phillies -122 (0.25u)**

---

## Skip / Fade

- **Brewers -162 vs Reds:** Drohan (3.12) is the better arm over Abbott (3.88), but -162 implies 61.8% and the model has MIL at 57.2%. Overpriced chalk — **pass**.
- **Rays -118 @ Royals:** Starters were unconfirmed at generation time, so there's no pitcher-driven model read. FanDuel's model leans Tampa Bay (55.9%). Monitor lineup cards; **no model play**.

---

## Parlay Suggestion (Optional, 0.25u)

Only one pick clears MEDIUM+ conviction today, so there's no strong multi-leg spot. A speculative **Marlins -126 + Phillies -122** value parlay (~+250) is the only reasonable combination for those wanting action.

---

## Summary Table

| Pick | ML | Conviction | Units | Edge |
|------|----|-----------|-------|------|
| Miami Marlins | -126 | MED-HIGH | 0.75u | +6.4% |
| Philadelphia Phillies | -122 | LEAN | 0.25u | +3.4% |
| **Total risk** | | | **1.0u** | |

*Discipline over volume: a short slate with limited edges means a small book today.*

---

*Pitcher stats & odds: FanDuel Research / Baseball-Reference (2026 season), as of the automated morning run. Model: ERA-differential + win% formula fallback (XGBoost available on Windows only). Odds move — confirm lines before betting.*
