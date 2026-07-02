# MLB Model — Triggers & Overlays Audit
*Generated 2026-06-29 | Model v2.1 + XGBoost rebuild*

---

## Part 1 — Current Active Triggers

These are the live rule overlays in `apply_rule_overlays()` inside `mlb_daily.py`, applied on top of the XGBoost base probability.

### 1. National TV Fade (+/- 3.5%)
**What it does:** When a game is on national TV (ESPN, FOX, FS1, TBS) and one team is the "marquee" side (typically the bigger market/star team), fades that team by -3.5% implied probability.  
**Rationale:** The market prices national TV games with extra juice on the popular/media-darling side. Public money piles in on recognizable teams in high-visibility slots, creating mild value on the other side.  
**Source:** Manual flag via `national_tv` and `marquee_side` fields in MANUAL_OVERLAYS.  
**Limitation:** Currently manual — not auto-detected from schedule data.

---

### 2. Short Rest Penalty (+/- 3%)
**What it does:** If a starter is pitching on ≤3 days rest, applies -3% to that team's win probability.  
**Rationale:** Starting pitchers on 3 days rest underperform their season ERA by roughly 0.5–0.8 runs on average. This is well-documented and consistently exploitable.  
**Source:** `away_rest` / `home_rest` from `mlb_data.py` starter data.

---

### 3. Extended Rest Rust Warning (flag only)
**What it does:** If a starter has 7+ days rest, appends a "rust risk" flag but does NOT adjust probabilities.  
**Rationale:** Extended rest (after a skip turn or injury layoff) has ambiguous effects — some starters stay sharp, others lose rhythm. Currently treated as a soft caution rather than a hard adjustment.  
**Upgrade candidate:** Could add -1.5% if also coming off an injury rehab stint.

---

### 4. IL Severity Score (+/- 4%)
**What it does:** Scores injured list impact (away_il_score, home_il_score). Score ≥10 → -4% to that team; ≥15 → -4% with a "heavy injury load" warning.  
**Rationale:** Injury load suppresses team performance beyond what ERA/record capture — especially when key lineup bats or bullpen arms are out.  
**Source:** Manual via MANUAL_OVERLAYS. Scale is approximate (e.g., 5pts = starting catcher, 3pts = bench bat).  
**Limitation:** Fully manual. No automated IL scrape yet.

---

### 5. Umpire Run Factor (O/U signal only)
**What it does:** If home plate umpire's historical run factor vs league avg is >+0.3, flags as hitter-friendly (Over lean); if <-0.3, flags as pitcher-friendly (Under lean).  
**Rationale:** HP umpire strike zone size and shape consistently affects run environment. Some umpires suppress runs by 0.5–1.0 per game vs league average.  
**Source:** `ump_run_factor` field from `mlb_data.py`'s `fetch_umpire_for_game()`.  
**Note:** Currently a flag and O/U signal only — does NOT adjust moneyline win probability. Could potentially affect home team (pitching with familiar zone) but effect size is small.

---

### 6. Pitcher Career ERA vs Opponent (BvP proxy, +/- 4%)
**What it does:** If a starter's career ERA against today's opponent is 1.5+ runs higher than his season ERA (minimum 15 IP sample), applies -4% to that team's win prob.  
**Rationale:** Career pitcher-vs-team trends are noisy at small samples but become meaningful at 15+ IP. A pitcher who consistently struggles against a specific lineup likely faces a matchup disadvantage.  
**Source:** Manual via `away_career_era_vs_opp` / `home_career_era_vs_opp` in MANUAL_OVERLAYS.  
**Limitation:** Fully manual. No automated BvP lookup yet.

---

### 7. ATS Ace Discount Warning (flag only)
**What it does:** If a starter's team is priced at -160 or worse ML AND that starter's ATS record is ≤35% over 10+ starts, flags as "ATS ACE DISCOUNT."  
**Rationale:** The market consistently overprices elite starters on moneyline. Teams going -160+ with a pitcher who only covers spread 35% of the time are offering poor moneyline value even if the starter is legitimately great.  
**Source:** `away_ats_w` / `away_ats_l` fields (manual).  
**Note:** Flag only — does not adjust probability. Could be wired to auto-apply -2% to -3% in a future version.

---

### 8. Day-After-Blowout (+/- 3%)
**What it does:** If a team won by 5+ runs the previous day, applies -3% to their win probability today.  
**Rationale:** "Blowout hangover" — manager may have used up the back of the bullpen, batters may be less focused after an easy win. Small but real effect in aggregate.  
**Source:** `day_after_blowout_team` field (manual or auto-computed from yesterday's game results in DB).

---

### 9. Rain / Weather Skip
**What it does:** If precipitation probability >60%, or if `rain_flagged=True` and precip >30%, flags the game as SKIP or CONDITIONAL.  
**Rationale:** Rain games are high-variance: postponements, early line movement, shortened innings. Model probabilities become unreliable for postponement risk.  
**Source:** `rain_pct` / `rain_flagged` fields (manual or from weather API).

---

### 10. Conviction Tiers & Run Line Gate
**What it does:** Not a probability adjustment, but a bet-sizing gate.
- Edges 2–5%: LEAN (0.25u)
- Edges 5–6%: MEDIUM (0.5u)
- Edges 6–8%: MED-HIGH (0.75u)
- Edges 8%+: HIGH (1.0u)
- Heavy favorites (-162+): forced to RUN LINE (no ML bet)
- Stale heavy favorites (-130 to -150) require 1 supporting criterion; (-150+) require 2 — else SKIP

---

## Part 2 — Model Features (XGBoost Layer)

These are embedded directly in the XGBoost model (not adjustments — the model learned their weights from historical data):

| Feature | What it captures |
|---|---|
| `fip_diff` / `away_fip_norm` / `home_fip_norm` | Fielding-independent pitching — luck-neutral ERA |
| `era_diff` / `away_era_norm` / `home_era_norm` | Observed ERA (includes defense/luck) |
| `bullpen_era_diff` / `away_bullpen_era_norm` / `home_bullpen_era_norm` | Bullpen quality (innings 6–9) |
| `away_qs_rate` / `home_qs_rate` / `qs_diff` | Quality start rate — starter reliability proxy |
| `win_pct_diff` | Season record gap between teams |
| `h2h_away_win_pct` | Head-to-head win% this season |
| `away_last10_runs` / `home_last10_runs` | Team offensive form — avg runs scored last 10 games |
| `park_factor` / `is_dome` | Run environment at this venue |
| `ump_run_factor` | HP umpire's historical run effect (continuous) |
| `rest_diff` / `away_short_rest` / `home_short_rest` | Days rest differential |

---

## Part 3 — Potential New Triggers

Ranked by estimated signal strength and implementation feasibility.

---

### HIGH PRIORITY

#### A. Bullpen Usage Last 3 Days (High Impact)
**What it does:** Flag if a bullpen has thrown 30+ IP in the last 3 days (combined relief appearances), especially if the closer pitched yesterday.  
**Rationale:** Bullpen fatigue is one of the most undervalued factors in public betting. A team that needed 4 relievers last night is dramatically more vulnerable today, and the market rarely adjusts fully for it.  
**Implementation:** Query the `bullpen` table + game logs for last 3 days. The data is already being collected.  
**Effect estimate:** -3% to -5% on a truly depleted bullpen.

#### B. Platoon Handedness Mismatch
**What it does:** If the starting pitcher and the opposing lineup are heavily stacked on the same hand (e.g., LHP vs lineup with 7 left-handed batters), flag as a platoon advantage/disadvantage.  
**Rationale:** Platoon splits are large and persistent — LHPs struggle against lineups loaded with LHH, and vice versa. The daily lineup construction often exploits this.  
**Implementation:** Requires lineup handedness data (MLB Stats API `/game/{pk}/liveData/boxscore` has batting handedness). Medium effort.  
**Effect estimate:** +2% to +4% for a clear platoon advantage.

#### C. Travel Distance / Time Zone Penalty
**What it does:** Apply a small penalty to teams that crossed 2+ time zones within the last 24 hours or have been on a road trip for 7+ consecutive days.  
**Rationale:** Travel fatigue is real and underappreciated by the market for series-openers after cross-country trips. "First game of road trip" overlaps with this.  
**Implementation:** Team schedule parsing — the MLB Stats API schedule endpoint has venue locations. Compute distance/time zone delta between yesterday's venue and today's.  
**Effect estimate:** -2% to -3% for 2+ time zone shifts within 24 hours.

#### D. Series Game Number
**What it does:** Flag game 3 or 4 of a series, especially for the home team in a multi-game series where starting rotation order is predictable.  
**Rationale:** By game 3-4 of a series, managers have burned through optimal lineup configurations, and starting rotation depth gaps widen. Home teams in short series often lose game 4 at elevated rates.  
**Implementation:** MLB Stats API schedule has series game number. Trivial to add.  
**Effect estimate:** Small (-1% to -2%), but automated.

---

### MEDIUM PRIORITY

#### E. Closer Availability
**What it does:** Flag games where the primary closer is unavailable (pitched 2+ consecutive days) or is on the IL.  
**Rationale:** Closer availability directly affects the "win probability in the 9th" calculation. A team without their closer in a 1-run game has a measurably lower win probability.  
**Implementation:** Combine bullpen usage data (already collected) with save situation probability. Medium complexity.  
**Effect estimate:** -2% in close-game scenarios (hard to apply without knowing game state in advance — could apply as a general flag).

#### F. Temperature Extremes (O/U signal)
**What it does:** Flag games where temperature is >90°F or <40°F as affecting run environment.  
**Rationale:** Baseball aerodynamics change significantly with temperature — cold air suppresses fly ball carry (Under lean), hot air boosts it (Over lean). This matters most at corner parks (Wrigley, Fenway, Coors).  
**Implementation:** Weather API already being used for rain. Adding temperature check is minimal added effort.  
**Effect estimate:** +/- 0.3 to 0.5 runs on totals; impacts Over/Under more than moneyline.

#### G. Turf vs. Grass Pitcher Splits
**What it does:** Flag pitchers who have large ERA splits between turf and grass (some sinkerballers are dramatically better on grass).  
**Rationale:** Turf fields produce different ground ball behavior, and some pitcher profiles (especially extreme ground ball pitchers) are measurably hurt by turf.  
**Implementation:** Stadium surface is static data (already partially tracked via `is_dome`). Pitcher turf/grass splits require FanGraphs or Baseball Reference lookup.  
**Effect estimate:** Small for most pitchers, occasionally large (-1.5+ ERA) for extreme profiles.

#### H. First Game After All-Star Break
**What it does:** Apply a small rust penalty in the first series back from the All-Star Break for pitching staffs coming off 4 days of inactivity.  
**Rationale:** Starters are often on irregular rest schedules coming off the break, and bullpens haven't been used in days. The first 2 games back historically show elevated run environments.  
**Implementation:** Static calendar — trivial to detect.  
**Effect estimate:** +0.2 runs to O/U; marginal moneyline effect.

---

### LOWER PRIORITY / EXPERIMENTAL

#### I. Manager Tendencies (Hook Rate)
**What it does:** Track which managers pull starters early vs. late, and factor in bullpen exposure per game.  
**Rationale:** Some managers hook starters at the first sign of trouble (increasing bullpen exposure), while others ride starters deep into games. This interacts with bullpen fatigue.  
**Implementation:** Historical game logs — requires building a per-manager dataset from past seasons. High effort.

#### J. Lineup Construction — Run Expectancy
**What it does:** Given today's confirmed lineup order, compute run expectancy based on lineup slot OPS/wOBA.  
**Rationale:** Lineup construction quality varies significantly day-to-day. A team resting 3 regulars has materially lower run expectancy than when fully healthy.  
**Implementation:** MLB Stats API live boxscore data has lineups once posted (~3–4 hours before first pitch). Medium effort.

#### K. Weather Wind Direction at Outdoor Parks
**What it does:** Wrigley Field, Fenway, and similar venues have dramatic wind effects on run scoring. Track wind direction and speed specifically at these venues.  
**Rationale:** At Wrigley, a 20mph out-to-left wind adds roughly 1.5 runs per game. This is already priced into some models but not all.  
**Implementation:** Weather API already in stack — adding wind direction is minimal. Stadium orientation data (static) required.

---

## Summary Table

| Trigger | Type | Currently Live | Effort to Add | Impact |
|---|---|---|---|---|
| National TV fade | Overlay | ✅ (manual) | Auto-detect | Medium |
| Short rest | Overlay | ✅ | — | High |
| Extended rest | Flag | ✅ | — | Low |
| IL score | Overlay | ✅ (manual) | Auto-scrape | High |
| Umpire run factor | Flag/O/U | ✅ | — | Medium |
| BvP career ERA | Overlay | ✅ (manual) | Auto-API | Medium |
| ATS ace discount | Flag | ✅ (manual) | Auto-track | Medium |
| Day-after-blowout | Overlay | ✅ | — | Low |
| Rain/weather | Skip flag | ✅ | — | High |
| Conviction tiers | Sizing | ✅ | — | — |
| Bullpen usage (3d) | Overlay | ❌ | Low | High |
| Platoon splits | Overlay | ❌ | Medium | High |
| Travel/time zone | Overlay | ❌ | Medium | Medium |
| Series game number | Flag | ❌ | Low | Low |
| Closer availability | Flag | ❌ | Medium | Medium |
| Temperature extremes | O/U flag | ❌ | Low | Medium |
| Turf/grass splits | Overlay | ❌ | High | Low |
| All-Star break rust | O/U flag | ❌ | Low | Low |
| Manager hook rate | Model feature | ❌ | High | Medium |
| Lineup run expectancy | Overlay | ❌ | Medium | High |
| Wind direction (key parks) | O/U flag | ❌ | Low | Medium |

---

*The three highest-ROI additions in order: (1) bullpen usage last 3 days — data already in DB, just needs a query; (2) platoon handedness — lineup data available from MLB API; (3) travel/time zone — schedule data already being pulled.*
