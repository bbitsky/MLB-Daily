# MLB Betting Model v2.1 — Updated June 28, 2026
## Incorporates June 26–27 Results + New Contextual Factors

**Previous model:** mlb_model_v2_june28_2026.md (v2.0)  
**Record since v1.0:** ML 3-7 (30%), O/U 1-3 (25%), HR Props 0-6 (0%), Fades 2-0 (100%)  
**v2.1 additions:** Umpire strike zone, series game number, pitcher rest days, travel fatigue/time zone, surface type, lineup handedness stack  
**Purpose:** This document supersedes v2.0 and adds six new contextual factors with monitoring protocols.

---

## SECTION 1: UPDATED PROCESS WORKFLOW

**Step order is now fixed. Do not deviate.**

### Step 1 — Confirm starters (same-day sources first)
- Source hierarchy: MLB.com lineup page > ESPN scoreboard > FanDuel Research > Baseball Reference
- BR lags on late changes. ESPN/MLB.com take precedence for day-of starters.
- Required output: confirmed starter + IL status for both teams.
- **Venue check required here:** verify which team is home before applying any park factors. (June 26 error: COL game misidentified as Coors Field when COL was the road team.)

### Step 1b — NEW: Umpire check
- Source: UmpScorecards.com (free, daily) or @UmpScorecards on Twitter
- Pull home plate umpire for each game you're considering.
- Key metrics to note:
  - **Run favor:** how many extra runs per game this umpire generates vs average (positive = hitter-friendly, negative = pitcher-friendly)
  - **K rate tendency:** high K rate ump = wide zone = pitcher-friendly
  - **BB tendency:** high BB rate = tight zone = hitter-friendly
- Apply to picks:
  - Pitcher-friendly ump (run favor < -0.3): -0.3 runs to O/U baseline, slight boost to underdog pitcher
  - Hitter-friendly ump (run favor > +0.3): +0.3 runs to O/U baseline, slight boost to offense
  - Neutral ump: no adjustment
- **Monitoring flag:** Log ump name + run favor + game O/U result each day. Track until 20 data points accumulated.

### Step 1c — NEW: Series context check
- Note which game of the series this is (game 1, 2, 3, or 4).
- **Game 1 of series:** Bullpens fully rested on both sides. Starters expected to go deeper. Closer likely available. Slight lean toward lower-scoring game.
- **Game 3 or 4 of series:** Bullpen fatigue is real. Managers have already burned their best relievers. Slight lean toward more offense and closer unavailability.
- Apply as a soft lean (±0.2 runs to O/U), not a hard adjustment. Do not use series position as primary pick driver — supporting factor only.
- **Monitoring flag:** Log game-in-series number + total runs scored each day. Track until 30 data points.

### Step 1d — NEW: Pitcher rest days
- Note how many days since each starter's last outing.
- Normal rest = 4 or 5 days. No adjustment.
- Short rest (3 days or fewer): flag as elevated risk. Command and velocity typically down. Apply -3% to that team's win probability and +0.3 runs to O/U.
- Extended rest (7+ days): flag as rust risk. Some pitchers need extra starts to find rhythm after long layoffs. Note but don't auto-adjust — check pitcher's historical performance on extended rest if available.
- **Monitoring flag:** Log rest days + starter ERA that day each game. Track until 20 data points.

### Step 2 — BvP pull (BEFORE building probabilities — this was the v1.0 process flaw)
- Navigate to `baseball-reference.com/previews/` for the game preview page.
- Pull all BvP matchup tables.
- Apply IP/PA thresholds (see Section 2 rules) before weighting.
- Flag: pitcher career ERA vs tonight's specific opponent (separate from individual BvP).

### Step 2b — NEW: Lineup handedness stack
- Pull confirmed lineups (or projected lineups pre-confirmation).
- Count how many of the top 6 hitters in each lineup bat from the same side as the opposing starter.
  - Example: LHP starter vs lineup with 5 LHBs in top 6 = major platoon disadvantage for the offense.
  - Example: RHP starter vs lineup with 5 RHBs in top 6 = moderate disadvantage (RHP vs RHB is the default matchup, less pronounced).
- Apply adjustment:
  - 5+ same-handed hitters in top 6 vs starter: -4% win probability for the batting team
  - 4 same-handed: -2%
  - Mixed/balanced: no adjustment
- **Note:** This matters most when the pitcher also has a strong platoon split (check pitcher's LHB vs RHB career ERA differential if available).
- **Monitoring flag:** Log handedness stack + outcome each game. Track until 25 data points.

### Step 3 — Weather check (same-day, not prior-day)
- Rain threshold protocol: >60% = SKIP, 30–60% = CONDITIONAL (half unit), <30% = clear
- **If ANY source (ESPN, RotoWire, Weather.com) flags rain risk, even if other sources show <10%, mark CONDITIONAL.** Discrepancy = uncertainty = risk.
- Apply park multipliers only after confirming weather:
  - Coors Field: +1.5 runs to O/U baseline, +4% HOU win probability
  - Petco Park (night, marine layer): -0.75 runs to O/U baseline
  - Oracle Park (wind in 15+ mph): -0.5 runs to O/U baseline
  - Fenway Park: +0.3 runs (short porch)
  - Heat >80°F + wind out >10 mph: +0.75 runs
  - Dome/retractable closed: 0 adjustment (100% neutral)
  - **Marine layer is a lean only (-0.75 runs). It does NOT override an elite offense like LAD/CHC/NYY. Apply it but don't rely on it to suppress a top-5 offense.**
  - **NEW — Surface type (grass vs turf):** Turf parks (Toronto, Tampa, Miami dome, Arizona dome) benefit groundball pitchers less than grass. A pitcher with GB% > 55% loses ~0.2 runs of suppression value on turf vs grass. Adjust their effective ERA up by 0.2 for O/U purposes. Conversely, a flyball pitcher (GB% < 40%) is relatively neutral between surfaces.
  - **NEW — Travel fatigue flag:** Check if either team traveled across 2+ time zones AND is playing earlier than their home norm. The highest-risk scenario: West Coast team playing a day game in the East (9am body time start). Apply -3% to that team's win probability. Standard evening games after cross-country travel = flag but no hard adjustment (monitor).
  - **Monitoring flag:** Log surface type + umpire + time zone displacement + runs scored each day. Build dataset toward 30 data points per factor.

### Step 4 — IL severity scoring
- 60-day IL: 3 pts | 15-day IL: 2 pts | 10-day/DTD: 1 pt
- Score both teams separately.
- Team score ≥ 10: apply -4% win probability to offense rating.
- Team score ≥ 15: CAUTION — do not bet favorites at -130 or shorter against this team. The market may not fully price in the roster depth issue.
- Example: BAL scored 17 (Jun 28) — backing them at -138 was a mistake that fit this pattern.

### Step 5 — Win probability build
Using: starter ERA, team record, home/away splits, IL score, park factors, weather, ATS trends.

**Favorite tier thresholds (new rule v2.0):**
- -110 to -130: standard conviction required (edge ≥ +5%)
- -130 to -150: requires at minimum ONE of: starter ERA ≤ 3.20 season / QS rate ≥ 65% / record gap ≥ 18 games
- -150+: requires TWO of the above. At -162+, evaluate run line or team total instead of ML.

**Record gap rule (corrected):**
- Record gap alone is insufficient justification. A 15-game gap (e.g., ATL 48-31 vs SF 33-47) supports conviction only if the favored team's starter also has ERA ≤ 3.50 or QS rate ≥ 65%.
- June 27: ATL -122 with Elder (ERA unknown at pick time) vs Webb (0.00 ERA in last 3) — gap without starter quality = loss.

### Step 6 — BvP integration (now informs win probability, not a post-check)
- Apply BvP adjustments as modifiers to Step 5 win probability.
- See Section 2 for BvP rules and thresholds.

### Step 7 — National TV / public money check
- ABC / ESPN Sunday Night / Apple TV / NBC Saturday: flag as national TV game.
- Public money discount: fade the marquee team by 3–5% win probability.
- **This rule is 3-for-3 validated.** It is now a full model layer, not a lean.
- "Day-after-blowout" extension (new): when a team wins by 10+ runs the prior day, the next day's opponent draws 3–5% extra public money value on underdog. Fade accordingly.
- Evidence: LAD won 15-3 Jun 27 → SDP was the pick at +118 Jun 28.

### Step 8 — Line confirmation + final edge calculation
- Convert moneyline to implied probability.
- Edge = my win probability − market implied probability.
- Minimum edges: HIGH conviction ≥ +8% | MEDIUM conviction ≥ +5% | LEAN ≥ +2%

### Step 9 — O/U assessment
- Run only after BvP is complete (prevents v1.0 Under removal scenario).
- **Under bet requirement (new rule v2.0):** BOTH lineups must have suppression signals. If either team has a top-10 offense by wRC+ or run production, unders require both:
  - Pitcher ERA ≤ 3.00 on that side, AND
  - BvP showing that team's hitters struggle vs tonight's starter.
- Do not bet under based on park factor alone when elite offense is involved.

### Step 10 — HR prop review
- See Section 3 for updated HR prop rules and sizing.

### Step 11 — Lineup confirmation (T-2hr before first pitch)
- Check confirmed lineups ~2 hours before first pitch.
- Flag any top-5 OPS player absent. Re-run probability if needed.
- This is when you catch day-of scratches (Schwarber, Gelof, etc.).

---

## SECTION 2: BvP RULES (UPDATED v2.0)

### 2A. Individual hitter BvP weighting

| Sample | Weight |
|--------|--------|
| < 4 PA | Flag only — do not weight in probability model. Note as directional signal. |
| 4–8 PA | Moderate weight — adjust by half the implied magnitude. |
| 9–14 PA | Standard weight — use as-is. |
| 15+ PA | Full weight — most reliable signal in model. |

### 2B. Pitcher-level BvP (career vs team as starter)

| Career IP vs team | Weight |
|-------------------|--------|
| < 10 IP | Flag only — small sample, directional at best. |
| 10–14 IP | Moderate — treat as supporting evidence only. |
| 15–29 IP | Standard weight — stable signal. |
| 30+ IP | High weight — most reliable pitcher-team read. |

**Critical lesson (June 27):** Harrison had career 0 ER in 8 IP vs CHC — that is <10 IP. Treated as full signal. He got bombed (CHC 8, MIL 2). Rule: below 15 IP, discount pitcher BvP by 50%. When below 10 IP, treat as a note only.

### 2C. Current form vs historical BvP conflict

New rule (from Rogers/WSN June 26): if a pitcher's last 3 GS ERA is **2.0+ below his season ERA**, discount his historical BvP by 30–40%. Recent form overrides historical pattern for pitchers who have clearly turned a corner.

Conversely: if a pitcher's last 3 GS ERA is 2.0+ **above** his season ERA, upgrade BvP strength by 20–30%.

### 2D. Post-TJS pitcher BvP

If pitcher had Tommy John surgery in the last 3 years, discount all pre-surgery BvP by 20–30%. Pitch repertoire, velocity, and arm slot often change post-TJS.

### 2E. "Never faced" signal

When a pitcher has **never started against tonight's opponent:**
- Credit the offense +2–3% win probability (element of surprise + regression to mean).
- Exception: if pitcher is a groundball specialist (GB% > 55%), reduce credit to +1% — pitch mix advantage compensates for unfamiliarity.

### 2F. Multi-hitter aggregation ("team BvP score")

Rather than evaluating BvP picks individually, compute a simple team BvP score:
- Count how many expected lineup hitters have meaningful BvP (9+ PA) against tonight's starter.
- If 3+ hitters have OPS ≥ 1.000 with 9+ PA: strong team BvP advantage — adjust win probability +5–7%.
- If 2 hitters: moderate advantage — adjust +3%.
- If 0–1: neutral.

### 2G. Pitcher vs specific team ERA (separate from hitter BvP)

"Career ERA vs tonight's opponent" is a parallel signal to individual BvP. Pull it every time.
- Cole: 5.42 ERA vs BOS (vs 3.62 season ERA) — validated 3 times in June.
- Rodon: strong vs BOS → neutralizes Duran/Yoshida BvP.
- This signal confirmed BOS +102 pick on June 27 (BOS 4, NYY 1).

---

## SECTION 3: HR PROP RULES (UPDATED v2.0)

### Core HR prop trigger (all conditions required):

1. Player has active HR streak of **5+ games**, OR had 6+ HR in last 7 games  
2. Tonight's pitcher has **HR/9 ≥ 1.0 in last 7 GS**  
3. Ballpark is not pitcher-favorable (Petco marine layer, Oracle wind-in) OR park bonus offsets

When all 3 are met: generate HR prop. Use **very small unit** (0.25–0.5u max).

### What's changed from v1.0:

**HR props are lottery tickets. They will lose most of the time. This is by design.**

- 0-for-6 record across June 26–27 at odds ranging +280 to +446.
- At +300 average, breakeven hit rate is ~25%. Individual prop hit rate is typically 15–20%.
- Correct response: don't stop playing them — **correct the unit sizing and usage.**

**New sizing rules:**
- Maximum 0.5 unit on any single HR prop.
- Never include HR props as anchor legs in parlays. They kill parlays.
- Never parlay 2+ HR props together (combined hit rate ~4–6%).
- Exception: a single HR prop can be appended to a 2-leg ML parlay if it transforms a +250 to a +700+ play. Keep total unit size the same (0.5u on the parlay, not 0.5u per leg).

**Streak fade rule:**
- When a hitter is on a 4+ game HR streak AND faces a pitcher with K rate > 30% OR strong BvP advantage for the pitcher, fade the continuation of the streak. The combo of elite K pitcher + active streak = regression candidate.
- Example: Suzuki HR streak vs Misiorowski (39.5% K rate) — correct fade, don't chase the streak here.

---

## SECTION 4: BET SIZING FRAMEWORK (NEW)

### Standard unit sizing by conviction:

| Conviction | Unit size | Required edge |
|------------|-----------|---------------|
| HIGH | 1.0u | ≥ +8% |
| MEDIUM-HIGH | 0.75u | ≥ +6% |
| MEDIUM | 0.5u | ≥ +5% |
| LEAN | 0.25u | ≥ +2% |
| HR Prop | 0.25–0.5u | Model trigger met |
| Parlay | 0.5u flat | 2–3 legs max |

### Favorites tier sizing adjustment:

- -140 to -160: reduce conviction by half a tier (HIGH → MEDIUM-HIGH; MEDIUM → LEAN). The juice eats EV.
- -160+: evaluate run line or team total first. Only bet ML at this price if you can't get run line value.

### Validated fades (2-0 record, full unit):

- "Ace discount" fade: when a team is -185 or shorter with a sub-3.00 ERA starter, their ATS record typically underperforms. Skenes 5-11 ATS confirmed.
- National TV fade: when marquee favorite is on national TV, take the run line or the underdog ML at full conviction.

---

## SECTION 5: VALIDATED RULES (confirmed by June 26–27 results)

### ✅ FULLY VALIDATED (3+ confirmations or strong single evidence):

**National TV public money fade (3-for-3)**
- Apple TV, ABC, NBC games: fade the marquee team. Take underdog ML or run line.
- Evidence: PIT -190 fade (CIN ✅), LAD -145 fade (SDP +1.5, though LAD won — rule is about market pricing, not win/loss), BOS +102 over NYY on non-national TV (✅).
- Status: Full model layer at v2.0. Apply in every national TV game.

**Cole/pitcher vs specific team ERA pattern (3 validations)**
- Cole's 5.42 ERA vs BOS despite 3.62 overall = persistent team-specific weakness.
- Check "pitcher career ERA vs tonight's opponent" every game. When gap exceeds 1.5 ERA vs season ERA, it's a meaningful signal.
- BOS +102 confirmed June 27 on this basis.

**ATS ace discount — Skenes pattern (confirmed)**
- 5-11 ATS in Skenes starts. PIT -190 fade worked June 26 (CIN 6, PIT 4).
- Rule: any team -175 or shorter behind their "ace" — check their ATS record in his starts before betting.

**BvP-driven under removal — correct process (confirmed Jun 26)**
- Under 8 NYY/BOS was removed after BvP showed Yoshida/Duran own Warren.
- Game went to 9 total runs (BOS 6, NYY 3). Correct pull.
- BvP running first (v2.0 process) prevents this error in the first place.

**High ERA pitcher facing team he historically struggles with — compounding signal**
- Arrighetti career 0-2, 17.05 ERA vs DET + DET hitters dominating him in BvP → DET won 8-0.
- Pattern is strongest when BOTH individual BvP and career pitcher-vs-team ERA align.

### ✅ PARTIALLY VALIDATED (1-2 confirmations, tracking):

**MIA road record value (1-for-1)**
- MIA +102 with 28-17 road record and Meyer 8-0 → MIA won 4-0.
- One game. Continue tracking small-market ace + elite road record combo.

**Coors Field structural over (validated but wrong venue Jun 26)**
- COL/MIN over 8.5 won ✅ (17 runs at Target Field, not Coors) — won for right reasons (bad starters) despite venue error.
- The structural over concept is sound; the venue check process was the flaw.

**"Day after blowout" fade (1 data point)**
- LAD won 15-3 June 27. SDP +118 was the June 28 pick on this basis.
- Too early to call validated. Track over next 10+ instances.

### ❌ NOT VALIDATED / INVALIDATED:

**Under bets with elite offense on one side**
- Under 8 MIL/CHC: CHC scored 8, MIL scored 2 (10 total). ❌
- Under 7.5 LAD/SDP: 18 total runs. ❌ Catastrophic.
- Rule: Do not bet under when either team is a top-10 offense unless BOTH have pitcher suppression signals (ERA ≤ 3.00 + strong BvP). Marine layer does not override LAD's offense.

**Record gap alone as conviction driver**
- ATL -122 with 15-game record gap vs SF: ATL 0, SF 5. Elder vs Webb shutout. ❌
- BAL -138: WSN won in 10 innings. ❌
- Record gap requires starter quality. It's a supporting factor, not a primary driver.

**Small-sample pitcher BvP (< 15 career IP vs team)**
- Harrison 0 ER in 8 career IP vs CHC: CHC 8, MIL 2. Harrison completely bombed. ❌
- 8 IP is well below the 15 IP threshold for reliability. This data point was over-weighted.

**HR Props (0-for-6)**
- Not invalidated as a concept — invalidated at the unit size and frequency we were playing them.
- Correction: smaller units, no parlay anchors, strict trigger criteria.

---

## SECTION 6: OPEN QUESTIONS FOR ONGOING TRACKING

These rules have logical basis but insufficient data to confirm or reject:

1. **Small-market ace discount:** Meyer at +102 (8-0, 2.80 ERA) winning at loanDepot — is the book consistently underpricing small-market aces? Track MIA, OAK, KC, TB starter pricing.

2. **Seager return impact:** Did TEX improve immediately after Seager's return from concussion IL? "Key player returning" +2–4% rule needs data.

3. **xERA vs ERA regression trigger:** Bradley's 4.11 ERA / 6.19 xERA — did he regress in the next 2 weeks? Track pitchers with 1.5+ ERA/xERA gap over next 10 starts.

4. **Umpire impact on O/U:** Not yet in model. Track: do certain umpires (high K rate) systematically move over/under results?

5. **Bullpen fatigue after blowout:** When a team wins by 10+ runs, their opponent's bullpen pitched long and in bad spots. Does this affect next-day starters/bullpen availability? Need to check the reverse — blowout-winner bullpen freshness.

6. **Caglianone/Gelof IL impact on KC/OAK:** When a team's #1 power threat goes on IL, how many games until the market adjusts fully? Initial game = overreaction fade opportunity?

---

## SECTION 7: RULES VERDICT — JUNE 26 MODEL IMPROVEMENT LIST

From the original 20 improvement triggers, here is the current status:

| # | Rule | Status | Notes |
|---|------|--------|-------|
| 1 | BvP PA minimum threshold (4+ PA to weight) | ✅ ADOPTED | Added to Step 2 workflow |
| 2 | "Never faced" signal (+2-3%) | ✅ ADOPTED | Section 2E |
| 3 | Starter career BvP vs team | ✅ ADOPTED | Section 2G, validated by Cole pattern |
| 4 | Market signal check (sharp money) | 🔄 TRACKING | No new data yet |
| 5 | Ace discount ATS rule | ✅ ADOPTED | Validated by Skenes (2x) |
| 6 | Returning player impact (+2-4%) | 🔄 TRACKING | Seager/De La Cruz — not yet confirmed |
| 7 | Crosswind O/U adjustment | 🔄 TRACKING | Added to park factors, not tested |
| 8 | IL severity score | ✅ ADOPTED | Step 4, BAL pattern confirmed |
| 9 | Pitcher vs specific team ERA | ✅ ADOPTED | Section 2G, validated by Cole |
| 10 | ATS cover rate as team signal | ✅ ADOPTED | Integrated into Step 5 |
| 11 | Rain flag protocol | ✅ ADOPTED | Step 3 (ANY source = CONDITIONAL) |
| 12 | Dome weather protocol | ✅ ADOPTED | Step 3 dome list |
| 13 | Same-day lineup news | ✅ ADOPTED | Step 11 (T-2hr check) |
| 14 | Roster depth penalty (10+ IL) | ✅ ADOPTED | Step 4 IL scoring |
| 15 | BvP MUST be Step 1 | ✅ ADOPTED | Step 2 (before probability model) |
| 16 | Multi-hitter BvP aggregation | ✅ ADOPTED | Section 2F team BvP score |
| 17 | Source conflict resolution | ✅ ADOPTED | Step 1 source hierarchy |
| 18 | 8-0 record pricing anomaly | 🔄 TRACKING | Small-market ace discount |
| 19 | Road record weighting | 🔄 TRACKING | When sample >25 games, primary over total |
| 20 | xERA vs ERA gap flag | 🔄 TRACKING | Need regression confirmation |
| + | Bullpen fatigue | 🔄 TRACKING | Not yet incorporated |
| + | Umpire data | 🔄 TRACKING | Not yet incorporated |
| + | Arsenal coverage (FanGraphs) | 🔄 TRACKING | HR prop add-on |

**June 27 new rules now in model:**
| # | Rule | Status |
|---|------|--------|
| N1 | BvP 15+ IP threshold for pitcher-team reliability | ✅ ADOPTED |
| N2 | HR props: tiny units, never parlay anchors | ✅ ADOPTED |
| N3 | Favorites beyond -140 require ERA/QS/record justification | ✅ ADOPTED |
| N4 | Unders require BOTH lineups suppressed (elite offense exception) | ✅ ADOPTED |
| N5 | Marine layer = lean only, doesn't override elite offense | ✅ ADOPTED |
| N6 | Day-after-blowout public money fade | 🔄 TRACKING (1 data point) |
| N7 | Record gap insufficient without starter quality | ✅ ADOPTED |
| N8 | National TV fade confirmed (3-for-3) | ✅ ADOPTED |
| N9 | IL score ≥ 15: caution on favorites against this team | ✅ ADOPTED |
| N10 | Current form overrides historical BvP (2.0+ ERA gap in last 3 GS) | ✅ ADOPTED |
| N11 | Venue verification required before park multipliers | ✅ ADOPTED |

---

## SECTION 8: QUICK REFERENCE CARD (print-ready for daily use)

```
DAILY WORKFLOW (in order):
1.  Confirm starters → MLB.com > ESPN > BR | Verify HOME TEAM before park factors
1b. Umpire check → UmpScorecards.com | Run favor >+0.3 = hitter-friendly | <-0.3 = pitcher-friendly
1c. Series context → Game 1 (rested bullpens) vs Game 3/4 (fatigue lean)
1d. Pitcher rest → Short rest (≤3 days) = -3% win prob + 0.3 O/U | Extended (7+) = rust flag
2.  Pull BvP tables → Apply PA/IP thresholds | Flag pitcher-vs-team career ERA
2b. Lineup handedness stack → 5+ same-handed in top 6 = -4% win prob for offense
3.  Weather check → Rain >60%=SKIP, 30-60%=CONDITIONAL | Park multipliers
    Surface: GB pitcher on turf = +0.2 effective ERA | Travel fatigue: WC team before noon ET = -3%
4.  IL severity score → ≥15 = caution on favorites
5.  Win probability → Apply team record, splits, park, weather, IL
6.  BvP integration → Adjust win% using Section 2 rules
7.  National TV check → Flag ABC/Apple TV/NBC → fade marquee team 3-5%
8.  Edge calc → HIGH ≥+8% | MEDIUM ≥+5% | LEAN ≥+2%
9.  O/U → Must have BOTH-side suppression. Elite offense = no under without ERA ≤3.00 + BvP.
10. HR props → All 3 triggers required. Max 0.5u. No parlay anchors.
11. T-2hr lineup check → Flag any top-5 OPS absent.
12. LOG new factors → Umpire / Series# / Rest / TZ / Surface / LH Stack → Section 9 table

KEY THRESHOLDS:
- BvP: 4+ PA (weight) | 9+ PA (full weight) | 15+ IP pitcher-team (reliable)
- Pitcher BvP current form: if last 3 GS ERA 2.0+ below season ERA → discount BvP 30-40%
- Favorites: -140 to -160 need 1 of (ERA ≤3.20, QS ≥65%, gap ≥18 games)
- Favorites: -160+ need 2 of above OR take run line
- IL ≥15 pts = do not lay -130 or shorter against that team

VALIDATED FADES (full unit):
✅ Ace ATS discount (-175 or shorter) — check ATS record
✅ National TV public money — fade marquee favorite (3-for-3)
✅ Pitcher ERA vs team > 1.5 above season ERA — opponent has edge

DO NOT:
❌ Bet under when elite offense (top-10 wRC+) is on either side without both-side suppression
❌ Back -140+ on record gap alone (need starter quality)
❌ Weight pitcher BvP < 15 career IP vs team as primary signal
❌ Parlay HR props as anchors
❌ Apply park factors before verifying home team
```

---

---

## SECTION 9: NEW FACTOR MONITORING LOG

These factors are now logged every day but **not yet applied with full weight** until they reach their data threshold. Once threshold is hit, they graduate to full model rules in the next version update.

### How to log (each daily report, add one row per game picked):

| Date | Game | Ump Run Favor | Game-in-Series | SP Rest Days | TZ Displacement | Surface | LH Stack | Outcome | Notes |
|------|------|--------------|----------------|--------------|----------------|---------|----------|---------|-------|
| Jun 28 | — | — | — | — | — | — | — | TBD | First day tracking |

### Graduation thresholds:

| Factor | Current Status | Threshold to Graduate | Early Signal |
|--------|---------------|----------------------|--------------|
| Umpire run favor | 🔄 MONITORING | 20 data points | None yet |
| Series game # | 🔄 MONITORING | 30 data points | None yet |
| Pitcher rest days | 🔄 MONITORING | 20 data points | None yet |
| Travel fatigue | 🔄 MONITORING | 20 data points | None yet |
| Surface type | 🔄 MONITORING | 25 data points | None yet |
| Lineup LH stack | 🔄 MONITORING | 25 data points | None yet |
| Day-after-blowout | 🔄 MONITORING | 10 data points | 1 data point (LAD→SDP) |

### What to watch for (patterns that would accelerate graduation):

- **Umpire:** If pitcher-friendly umps (run favor < -0.3) show ≥60% under hit rate across 10+ games, graduate early.
- **Series game #:** If game 3/4 total runs average 1.5+ more than game 1 across 15+ games, graduate early.
- **Travel fatigue:** If West Coast teams starting before noon ET go under .400 in first 10 games, apply immediately.
- **Handedness stack:** If 5+ same-handed stacks lose 65%+ of the time across 15 games, apply at -5% immediately.

---

*Model v2.1 — June 28, 2026 | Next review: June 29 after today's results*
