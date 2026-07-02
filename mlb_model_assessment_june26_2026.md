# MLB Full Model Assessment — June 26, 2026
## For Cowork Project: Model Refinement & Process Improvement

**Purpose:** This document contains the full game-by-game assessment from the June 26 analysis session, including all model inputs, confidence levels, BvP findings, and explicit model improvement triggers for each game. Use this alongside the picks log to calibrate the model going forward.

---

## MODEL ARCHITECTURE (current as of June 26, 2026)

### Input layers (in order applied this session):
1. **Pitcher quality** — ERA, W-L, last 7 GS trend, career splits
2. **Team record & recent form** — overall, last 10/20/30, home/away
3. **Weather** — indoor=100pts neutral, wind out=offense boost, wind in=pitcher boost, rain=risk flag
4. **Injuries** — IL players weighted by lineup impact (60-day > 15-day > DTD)
5. **Market implied probability** — moneyline converted to implied %
6. **Edge calculation** — my % minus market implied %
7. **BvP check** — applied AFTER initial model (identified as process flaw — see improvements section)
8. **Social/streak intel** — last-minute scratches, HR streaks, hot hitters
9. **ATS/underdog trends** — team cover rates, underdog win rates

### Known model gaps identified this session:
- BvP applied too late (after initial probability, not before)
- Weather data was from June 25 (one day stale) — need same-day source
- No bullpen fatigue model
- No umpire data incorporated
- No lineup confirmation step (lineups post ~2hrs before game)
- Small-sample BvP (2-3 PA) weighted same as large-sample (9+ PA)

---

## GAME-BY-GAME FULL ASSESSMENT

---

### GAME 1: HOU Astros @ DET Tigers — 6:40 PM ET
**Venue:** Comerica Park, Detroit (outdoor)

#### Model inputs:
| Factor | HOU | DET |
|--------|-----|-----|
| Starter | Arrighetti (7-3, 3.13 ERA) | Montero (3-5, 3.68 ERA) |
| Last 7 GS ERA | 4.02 | 4.08 |
| Team record | 40-43 | 34-47 |
| Last 10 | 7-3 | 5-5 |
| Last 30 | 18-12 | 14-16 |
| Road/Home record | 20-22 away | 22-19 home |
| vs RHP/LHP | 30-30 vs RHP | 25-30 vs RHP |
| IL impact | Moderate | HEAVY (Báez, Torres, Flaherty, Olson, Meadows all IL) |
| Weather | 71°F, 13mph crosswind, 12% rain risk | — |
| Season series | HOU leads 3-1 in 2026 | — |

#### BvP findings (pulled from BR preview page):
**DET hitters vs Arrighetti:**
- Riley Greene (LHB): 5 PA, **3.000 OPS** ← large enough sample, massive flag
- Colt Keith (LHB): 4 PA, **2.000 OPS** ← meaningful sample
- James Outman (LHB): 2 PA, **5.000 OPS** ← too small to weight heavily
- Jace Vierling: 2 PA, **2.500 OPS** ← small sample
- Arrighetti career vs DET as starter: **0-2, 17.05 ERA** (6.1 IP — small but directionally bad)

**HOU hitters vs Montero:**
- Isaac Paredes: 5 PA, **1.800 OPS** ← significant
- Christian Vázquez: 5 PA, **1.800 OPS** ← significant
- Montero has **NEVER faced HOU as starter** ← unknown = slight positive for HOU

**BvP net verdict:** DET has BvP edge via LHBs. HOU has counter-edge via Paredes/Vázquez.

#### Market:
- HOU: -102 | DET: -118
- Market making DET a slight favorite despite worse record — suggests sharp money on DET or public fading HOU's road record

#### Model assessment:
- **Initial win probability:** HOU 56%, DET 44%
- **Post-BvP adjustment:** HOU 52%, DET 48%
- **Edge after adjustment:** HOU +2% (from +6% pre-BvP) — below threshold for full conviction
- **Pick:** HOU -102 (reduced unit) ← downgraded from high to medium

#### Model improvement triggers from this game:
- [ ] **BvP weight rule needed:** Greene's 5 PA at 3.000 OPS should carry more weight than Outman's 2 PA at 5.000. Implement minimum PA threshold: weight BvP only if 4+ PA. Flag but don't weight if <4 PA.
- [ ] **"Never faced" signal:** Montero never facing HOU is a slight positive for HOU offense (unknown = regression to mean). Codify this as +2-3% edge for the team facing the unknown pitcher.
- [ ] **Starter career BvP vs team:** Arrighetti's 0-2 / 17.05 ERA vs DET as a starter is a separate signal from individual BvP. Add "starter's team BvP record" as a model input.
- [ ] **Market signal check:** When market favors the team with the worse record AND worse starter (DET -118 despite Montero 3.68 vs Arrighetti 3.13), that's a sharp-money signal worth flagging.

---

### GAME 2: CIN Reds @ PIT Pirates — 6:40 PM ET
**Venue:** PNC Park, Pittsburgh (outdoor)

#### Model inputs:
| Factor | CIN | PIT |
|--------|-----|-----|
| Starter | Abbott (5-4, 3.83 ERA) | Skenes (6-7, 2.86 ERA) |
| Team record | 37-42 | 41-40 |
| Last 10 | — | — |
| IL impact | Elly De La Cruz recently returned (hamstring) | Moderate |
| Weather | 77°F, 15mph R→L crosswind | — |

#### BvP: Not pulled this session.

#### Market:
- PIT: -190 | CIN: +160
- O/U: 7.5

#### Model assessment:
- **Win probability:** PIT 60%, CIN 40%
- **Market implied:** PIT 66%, CIN 38%
- **Edge:** CIN +2% (slight value at +160)
- **Pick:** CIN +160 small speculative unit (underdog value)
- **Fade signal:** PIT -190 is overpriced — Skenes' team is 5-11 ATS in his starts

#### Model improvement triggers:
- [ ] **Ace discount rule:** When a true ace starts (sub-3.00 ERA), the market overprices the team. Skenes' team going 5-11 ATS in his starts is a structural inefficiency. Add "starter ATS record" as a model layer — particularly for elite starters where market overreacts to name value.
- [ ] **Returning player impact:** De La Cruz returning from IL. Need a model input for "key player returning from injury" — especially a leadoff/top-of-order bat. Should add 2-4% to team win probability in first few games back.
- [ ] **O/U with crosswind:** 15mph R→L crosswind at PNC. Need to codify: R→L = ball carries to left-center, slight hitter's advantage. Should adjust O/U assessment slightly upward.

---

### GAME 3: WSN Nationals @ BAL Orioles — 7:05 PM ET
**Venue:** Oriole Park at Camden Yards (outdoor)
**Status: TOP VALUE PICK**

#### Model inputs:
| Factor | WSN | BAL |
|--------|-----|-----|
| Starter | Alvarez (1-0, 3.34 ERA) | Rogers (4-7, 5.30 ERA) |
| Last 7 GS ERA | Alvarez: 2.67 | Rogers: 4.89 |
| Team record | 41-41 | 38-44 |
| Last 10 | 4-6 | 4-6 |
| Road record | WSN 24-16 away ← excellent | BAL 22-19 home |
| Underdog win rate | WSN 51% as underdogs this year | — |
| ATS cover rate | WSN 48-32 (60%) — best MLB | BAL 40-42 |
| vs LHP | WSN 16-9 vs LHP | — |
| IL impact | Low | DEVASTATING: Mountcastle (60-day), Westburg (season), Eflin (60-day), Kremer (60-day), Bassitt (15-day), Beavers (10-day) |
| Weather | 85°F, wind OUT to LF, 1% rain | — |
| Season series | WSN leads 2026 2-1 | — |

#### BvP findings (pulled from BR preview page):
**WSN hitters vs Rogers (LHP):**
- CJ Abrams (LHB): **9 PA, 1.556 OPS** ← large sample, elite ownership
- James Wood (LHB): **3 PA, 2.000 OPS** ← small but positive
- Trea Mead: **2 PA, 2.000 OPS** ← small
- Chaparro: **2 PA, 1.500 OPS** ← small
- Rogers career vs WSN: **1-3, 5.09 ERA** in last 5 starts
- Alvarez has **NEVER faced BAL** ← clean slate

**BAL hitters vs Alvarez (LHP):**
- Most BAL hitters have NO BvP history vs Alvarez
- Pete Alonso: 4/1.000 — decent but not dominant
- Henderson: 1/0.000, Holliday: various small samples
- **Net: BAL offense largely unknown vs Alvarez — regression to mean**

#### Market:
- WSN: +120 | BAL: -142
- O/U: 9

#### Model assessment:
- **Initial win probability:** WSN 57%, BAL 43%
- **Post-BvP adjustment:** WSN 61%, BAL 39% (BvP upgrade — Abrams/Wood/Mead own Rogers)
- **Market implied:** WSN 45%
- **Edge:** WSN +16% ← strongest edge on slate
- **Pick:** WSN +120 HIGH conviction + Over 9 lean + CJ Abrams HR prop

#### Model improvement triggers:
- [ ] **Weather-offense multiplier:** 85°F + wind blowing out to LF = significant run environment boost. Need explicit multiplier in O/U model — suggest +0.5 to +1.0 runs added to total when temp >80°F AND wind out >10mph.
- [ ] **Team IL severity score:** BAL has 6 significant IL entries including two 60-day. Need a formal IL severity score (60-day=3pts, 15-day=2pts, 10-day=1pt, DTD=0.5pt) that adjusts team offense/defense rating. BAL's IL score this game would be among highest in MLB.
- [ ] **Pitcher-vs-team history:** Rogers 1-3 / 5.09 ERA in last 5 vs WSN is a strong signal. "Pitcher career record vs specific team" should be a model layer weighted alongside ERA.
- [ ] **ATS cover rate as signal:** WSN's 60% cover rate (48-32-0) is the best in MLB. This is a meaningful team-level trend that should add 2-3% to win probability assessments when a team is in top quartile of ATS performance.
- [ ] **⚠️ Rain risk protocol:** ESPN flagged this game for rain despite 1% precipitation shown on RotoWire. Discrepancy between sources. Need a rule: if ANY source flags rain risk, mark pick as CONDITIONAL and note it prominently. Don't bury rain flags.

---

### GAME 4: TEX Rangers @ TOR Blue Jays — 7:07 PM ET
**Venue:** Rogers Centre, Toronto (DOME — roof closed due to T-storms)

#### Model inputs:
| Factor | TEX | TOR |
|--------|-----|-----|
| Starter | Eovaldi (7-7, 4.24 ERA) | Corbin (2-3, 4.73 ERA) |
| Team record | 39-42 | 39-42 |
| IL impact | Seager returned from concussion IL today | TOR: league-high 17 players on 60-day IL |
| Weather | DOME — 100pts neutral | — |
| Season series | — | — |

#### BvP: Not pulled this session.

#### Market:
- TEX: -112 | TOR: -104
- O/U: 7.5

#### Model assessment:
- **Win probability:** TEX 54%, TOR 46%
- **Market implied:** TEX 53%, TOR 49%
- **Edge:** TEX +1% — essentially fair, no play
- **Pick:** Pass / no edge
- **Seager return note:** Late-breaking positive for TEX — Seager's return boosts lineup meaningfully but not captured in initial model

#### Model improvement triggers:
- [ ] **Dome weather protocol:** Indoor stadiums (Rogers Centre, Chase Field, Tropicana, Marlins Park, Minute Maid retractable) should auto-score 100pts weather neutral. Build explicit dome list into model — don't rely on RotoWire flagging it each time.
- [ ] **Same-day lineup news integration:** Seager returning from concussion IL was announced day-of. This is a significant lineup upgrade that should trigger a re-run of the model. Need a formal "lineup confirmation window" — check lineups ~2 hours before first pitch and flag any meaningful changes that weren't in original assessment.
- [ ] **Roster depth penalty:** TOR's 17 players on 60-day IL is an extreme roster stress signal. Even if starters are healthy, bullpen and bench depth matter. Need a "roster depth score" that penalizes teams with 10+ players on IL.

---

### GAME 5: NYY Yankees @ BOS Red Sox — 7:10 PM ET
**Venue:** Fenway Park, Boston (outdoor)

#### Model inputs:
| Factor | NYY | BOS |
|--------|-----|-----|
| Starter | Warren (7-2, 3.45 ERA) | Tolle (3-5, 3.08 ERA) |
| Last 7 GS ERA | Warren: 3.44 | Tolle: 3.67 |
| Team record | 48-32 | 33-46 |
| Last 10 | 5-5 | 4-6 |
| Last 30 | 18-12 | 11-19 |
| Warren ATS | 9-6 in his starts | — |
| Tolle ATS | 2-9 in his starts | — |
| vs LHP | NYY 19-10 | — |
| Weather | 80°F, 6mph wind out to LF, 2% rain | — |
| Judge status | OUT (not in lineup) | — |
| Season series | NYY leads 4-2 in 2026 | — |

#### BvP findings (pulled from BR preview page):
**BOS hitters vs Warren:**
- Masataka Yoshida (LHB): **5 PA, 1.350 OPS** ← significant, meaningful sample
- Jarren Duran (LHB): **9 PA, 1.083 OPS** ← large sample, clear ownership pattern
- Narváez: 8/1.625 OPS — catcher owning Warren (8 PA = meaningful)
- Warren career vs BOS: **9.42 ERA in last 5 meetings** ← alarming, small sample
- **Key insight: Warren has a BOS problem — multiple hitters own him in meaningful samples**

**NYY hitters vs Tolle (LHP):**
- Jazz Chisholm: 2 PA, 2.500 OPS — tiny sample
- Most NYY bats have no Tolle history
- Goldschmidt: no BvP vs Tolle but 8/14 HR vs LHP this season

#### Market:
- NYY: -110 | BOS: -106
- O/U: 8

#### Model assessment:
- **Initial win probability:** NYY 65%, BOS 35%
- **Post-BvP adjustment:** NYY 60%, BOS 40%
- **Market implied:** NYY 52%, BOS 49%
- **Edge:** NYY +8% — still positive but BvP narrowed it
- **Pick:** NYY -110 ML (maintain, medium conviction)
- **Under 8 REMOVED after BvP:** Yoshida + Duran + Narváez all own Warren. BOS will score.

#### Model improvement triggers:
- [ ] **BvP must precede O/U model:** If we had run BvP FIRST, we never would have suggested Under 8. The BvP data directly contradicted the under. BvP MUST be step 1, not step 7. **This is the single biggest process flaw identified this session.**
- [ ] **Multi-hitter BvP aggregation:** Instead of flagging individual BvP, need a "team BvP score" — aggregate OPS of expected lineup vs starting pitcher, weighted by PA count. If multiple lineup regulars have >1.000 OPS with meaningful PA, that's a strong signal.
- [ ] **Pitcher vs specific team ERA:** Warren's 9.42 ERA in last 5 vs BOS is a red flag even though his overall ERA is 3.45. "Pitcher's ERA vs tonight's opponent specifically" should be a model layer.
- [ ] **Judge absence:** Aaron Judge is out. This is a major lineup subtraction for NYY — their best hitter. Need to explicitly model "key player absent" — particularly cleanup/3-4-5 hitters. Estimate run production loss based on their OPS and lineup position.

---

### GAME 6: SEA Mariners @ CLE Guardians — 7:10 PM ET
**Venue:** Progressive Field, Cleveland (outdoor)

#### Model inputs:
| Factor | SEA | CLE |
|--------|-----|-----|
| Starter | Castillo (2-6, 5.22 ERA) | Cantillo (6-3, 4.05 ERA) |
| Team record | 41-41 | 42-39 |
| Arozarena | OUT (hamstring IL) | — |
| Castillo ATS | 3-9 in his starts | — |
| Cantillo ATS | 12-4 in his starts ← excellent | — |
| Weather | ~72°F, rain risk flagged by ESPN | — |

#### BvP: Not pulled this session.

#### Market:
- CLE: -112 | SEA: -104

#### Model assessment:
- **Win probability:** CLE 58%, SEA 42%
- **Market implied:** CLE 53%, SEA 49%
- **Edge:** CLE +5%
- **Pick:** No play — rain risk + insufficient BvP review
- **Travis Bazzana prop noted:** 1.202 OPS last 30 PA vs RHP, vs Castillo (below-avg pitch mix) — but rain risk makes this conditional

#### Model improvement triggers:
- [ ] **ATS starter trend:** Cantillo's team going 12-4 ATS in his starts is a strong systematic signal. "Starter ATS record in 2026" should be a standard model input alongside ERA.
- [ ] **Injured OF impact:** Arozarena (10-day IL, hamstring) is SEA's best outfield bat. Any top-3 OPS player missing should automatically adjust team run expectation downward by estimated 0.3-0.5 runs per game.
- [ ] **Rain flag from secondary source:** ESPN flagged this game for rain even though base weather showed moderate conditions. Protocol: if rain flag appears in ANY source (ESPN, RotoWire, weather services), auto-downgrade to conditional pick.

---

### GAME 7: PHI Phillies @ NYM Mets — 7:10 PM ET
**Venue:** Citi Field, Flushing (outdoor)

#### Model inputs:
| Factor | PHI | NYM |
|--------|-----|-----|
| Starter | Wheeler (7-1, 2.11 ERA) | Thornton (0-1, 8.31 ERA) |
| Last 7 GS ERA | Wheeler: 1.85 ← elite | Thornton: one start |
| Team record | 45-36 | 34-47 |
| Last 10 | 7-3 | 2-8 |
| Last 30 | 20-10 | 12-18 |
| Schwarber status | QUESTIONABLE (back tightness) | — |
| Weather | 78°F, 15mph wind R→L (out to LCF), 2% rain | — |
| Lindor status | On IL (Mets) | — |
| Season series | PHI leads 2-1 | — |

#### BvP findings (pulled from BR preview page):
**NYM hitters vs Wheeler:**
- Juan Soto (LHB): **67 PA, 0.879 OPS** ← largest sample, .879 is solid but not dominant for Soto's caliber
- Francisco Lindor (switch): **37 PA, 0.738 OPS** ← average, Wheeler handles him (Lindor on IL anyway)
- Brett Baty (LHB): **14 PA, 0.786 OPS** ← average
- Mark Vientos: **9 PA, 0.777 OPS** ← average
- **Net: No NYM bat truly dominates Wheeler. Soto is the only real threat.**

**PHI hitters vs Thornton (LHP):**
- **Thornton has NEVER faced PHI** ← complete unknown
- PHI lineup context vs NYM bullpen:
  - Bohm: 10/1.200 vs Brazoban
  - Realmuto: 8/1.232 vs Brazoban
  - Turner: 10/1.500 vs Weaver
  - **PHI will tee off on NYM bullpen late game**

#### Market:
- PHI: -162 | NYM: +136
- O/U: 8

#### Model assessment:
- **Win probability:** PHI 83%, NYM 17%
- **Market implied:** PHI 62%, NYM 43%
- **Edge:** PHI +21% — but market is correct at -162 given risk/reward
- **Pick:** PHI -162 is fair price. No overlay value at that price.
- **Better play:** PHI -1.5 run line (+106) or PHI team total over
- **Schwarber note:** If scratched (back), PHI win probability drops ~5%

#### Model improvement triggers:
- [ ] **Price vs edge distinction:** Having +21% edge doesn't mean -162 is the right bet. Need a Kelly criterion or bet-sizing rule based on implied probability vs true probability — at -162 you need to win 62% to break even, and even if you're right at 83%, the payout is poor. The run line or team total is higher EV.
- [ ] **"Never faced" for rookie/debut starters:** Thornton has 1 career start. This is an extreme version of "limited data" — model should flag single-start pitchers as high variance and widen the probability distribution.
- [ ] **Schwarber scratch protocol:** MLB's designated hitter/key bat scratches happen frequently day-of. Need a formal "check lineup 2hrs before first pitch" step that specifically flags if top-5 OPS players are in/out. Schwarber's scratch would be the most impactful lineup change on tonight's slate.
- [ ] **Wind at Citi Field:** 15mph wind blowing out to LCF = homer-friendly. Should boost O/U assessment slightly. Combined with 78°F, this is a moderate hitter's environment.

---

### GAME 8: ARI D'backs @ TBR Rays — 7:10 PM ET
**Venue:** Chase Field, Phoenix (DOME — retractable)

#### Model inputs:
| Factor | ARI | TBR |
|--------|-----|-----|
| Starter | Gallen (3-6, 6.10 ERA) | Martinez (6-2, 2.73 ERA) |
| Team record | 41-39 | 45-33 |
| Weather | Dome — 100pts neutral | — |

#### BvP: Not pulled this session.

#### Market:
- TBR: favorite | ARI: underdog (~even to slight)
- O/U: 8

#### Model assessment:
- **Win probability:** TBR 62%, ARI 38%
- **Market implied:** TBR ~55%, ARI ~45%
- **Edge:** TBR +7% — slight value but didn't make our picks list
- **Pick:** No play (didn't meet conviction threshold)

#### Model improvement triggers:
- [ ] **ERA gap threshold:** Martinez 2.73 vs Gallen 6.10 is a 3.37 ERA gap — among the largest on tonight's slate. Need a formal "ERA gap rule": when gap exceeds 2.5, auto-flag for deeper review regardless of team records. This game deserved more attention.
- [ ] **Rays analytical advantage:** Tampa Bay consistently outperforms market expectations due to roster management and analytics. Consider a small "franchise multiplier" for teams with proven analytical edges (TB, HOU, LAD) when lines are close.

---

### GAME 9: KCR Royals @ CHW White Sox — 7:40 PM ET
**Venue:** Guaranteed Rate Field, Chicago (outdoor)

#### Model inputs:
| Factor | KCR | CHW |
|--------|-----|-----|
| Starter | Cruz (1-2, 6.26 ERA) | Sandlin (1-1, 8.10 ERA) |
| Team record | 34-48 | 41-38 |
| Caglianone | 6 HR in last 7 games, .699 SLG June | — |
| Sandlin HR/9 | — | 2.70 HR/9, 4 HR in 3 starts |
| Weather | ~78°F, moderate winds | — |

#### BvP: Not pulled this session.

#### Model assessment:
- **Win probability:** CHW 53%, KCR 47%
- **Market implied:** ~even
- **Edge:** Minimal — no moneyline play
- **Key insight:** Both starters ERA 6.0+ = high-scoring game expected. O/U over 9 lean.
- **Individual prop:** Caglianone HR (+400) is the standout play in this game

#### Model improvement triggers:
- [ ] **"Dual bad starter" O/U model:** When BOTH starters have ERA above 5.50, the O/U should automatically be flagged for over assessment regardless of team records. High ERA + park factors = run environment.
- [ ] **HR/9 pitcher metric:** Sandlin's 2.70 HR/9 and Caglianone's 6-in-7 streak creates a perfect prop storm. Need "pitcher HR/9 rate" as a standard input for HR prop assessments. Any pitcher with HR/9 > 2.0 should auto-flag as HR prop opportunity.
- [ ] **Hot streak + favorable matchup = prop trigger:** Caglianone (6 HR in 7 games) + Sandlin (2.70 HR/9) is the clearest prop value on the slate. Need a formal rule: when player is on 5+ game power streak AND facing pitcher with HR/9 > 1.8, auto-generate HR prop recommendation.

---

### GAME 10: CHC Cubs @ MIL Brewers — 7:45 PM ET
**Venue:** American Family Field, Milwaukee (outdoor)

#### Model inputs:
| Factor | CHC | MIL |
|--------|-----|-----|
| Starter | Rea (5-5, 4.99 ERA) | Misiorowski (8-3, 1.45 ERA) |
| Team record | 44-37 | 49-29 |
| CHC IL | Brown (neck, 15-day), Cabrera (hamstring, 15-day), Palencia (flexor) | — |
| Misiorowski K rate | — | 39.5% strikeout rate — best in MLB |
| Seiya Suzuki | 4-game HR streak | Faces Misiorowski |
| Weather | ~78°F, wind out to CF | — |

#### BvP: Not pulled this session.

#### Model assessment:
- **Win probability:** MIL 73%, CHC 27%
- **Market implied:** MIL ~64%
- **Edge:** MIL correctly priced or slight overlay
- **Pick:** No play — MIL price too short for value
- **Key narrative:** Suzuki's 4-game HR streak vs Misiorowski (39.5% K rate) = fade the streak play
- **Misiorowski as streak record threat:** One K away from challenging single-game records

#### Model improvement triggers:
- [ ] **Streak fade rule:** When a hitter on a 4+ game HR streak faces a pitcher with K rate > 30%, the streak is more likely to end than continue. Need explicit "streak vs elite pitcher" fade trigger.
- [ ] **Multiple IL starters for same team:** CHC losing Brown AND Cabrera in the same week is a double-blow to the rotation. When a team loses 2+ rotation pieces within 7 days, apply a bullpen stress multiplier to their run prevention ability.
- [ ] **K rate as HR prop negative:** Misiorowski's 39.5% K rate is a direct counter to HR prop value for CHC hitters. Formalize: if pitcher K rate > 30%, reduce HR prop probability for opposing hitters by ~40%.

---

### GAME 11: COL Rockies @ MIN Twins — 8:10 PM ET
**Venue:** Coors Field, Denver (outdoor, HIGH ALTITUDE)

#### Model inputs:
| Factor | COL | MIN |
|--------|-----|-----|
| Starter | Sugano (8-4, 4.31 ERA) | Bradley (6-3, 4.11 ERA) |
| Team record | 32-49 | 38-44 |
| Coors effect | Home team benefits from altitude familiarity | — |
| TJ Rumfield | .692 SLG, 1.092 OPS last 60 AB vs RHP | — |
| Bradley xERA | 6.19 (recent starts) | — |
| Weather | ~80°F, high altitude | — |

#### BvP: Not pulled this session.

#### Model assessment:
- **Win probability:** COL 46%, MIN 54% (Coors park factor brings COL closer to even despite worse record)
- **Market implied:** ~50/50
- **Edge:** Minimal ML edge. O/U over 8.5 is the play.
- **Pick:** Over 8.5 (structural Coors lean) + TJ Rumfield HR prop

#### Model improvement triggers:
- [ ] **Coors Field park multiplier:** Every game at Coors needs an automatic run environment boost. Suggest: add 1.5 runs to expected total before any other calculation. This is the most predictable park effect in baseball. Also apply to home team win probability (+3-5% for COL at home).
- [ ] **xERA vs ERA for recent form:** Bradley's ERA is 4.11 but his xERA in recent starts is 6.19 — a 2+ run gap indicating regression incoming. Need to incorporate xERA/FIP alongside ERA in pitcher quality assessment. When xERA > ERA by 1.5+, flag as overperformer due for regression.
- [ ] **HR prop at Coors:** Any hitter with recent power form at Coors should get an automatic HR prop boost. Rumfield's 1.092 OPS + Coors + Bradley's 6.19 xERA = textbook prop opportunity.

---

### GAME 12: MIA Marlins @ STL Cardinals — 8:15 PM ET
**Venue:** loanDepot Park, Miami (DOME)

#### Model inputs:
| Factor | MIA | STL |
|--------|-----|-----|
| Starter | Meyer (8-0, 2.80 ERA) | May (5-6, 4.30 ERA) — ESPN confirmed |
| Team record | 42-39 | 42-36 |
| Road record | MIA **28-17 away** ← outstanding | STL 22-19 home |
| Arraez | — | OUT (foot contusion) |
| Owen Caissie | 27.8% barrel rate, 1.012 OPS last 30 PA vs RHP | — |
| Weather | Dome — 100pts neutral | — |

#### BvP: Not pulled this session (STL page not scraped).

#### Market:
- MIA: +102 | STL: -122
- O/U: 8

#### Model assessment:
- **Win probability:** MIA 58%, STL 42%
- **Market implied:** MIA 45%, STL 55%
- **Edge:** MIA +13% ← second strongest edge on slate
- **Pick:** MIA +102 HIGH conviction
- **Note:** ESPN showed STL starter as Dustin May (5-6, 4.30) — not McGreevy as Baseball Reference listed. Source conflict resolved in favor of ESPN same-day data.

#### Model improvement triggers:
- [ ] **Source conflict resolution protocol:** BR listed McGreevy, ESPN showed May. Need explicit rule: for starting pitcher confirmation, prefer same-day sources (ESPN, MLB.com lineups) over Baseball Reference (which may lag on late changes). Always cross-reference starter before finalizing picks.
- [ ] **8-0 record pricing anomaly:** Max Meyer at 8-0 with 2.80 ERA being priced as an underdog (+102) is a systematic market inefficiency. Hypothesis: small-market team discount — books underprice small-market team aces relative to large-market counterparts. Track this pattern across multiple sessions to validate.
- [ ] **Road record as strong signal:** MIA's 28-17 road record is outstanding. Team road record (when >55%) should receive more weight in the model — currently treated as one of many inputs but may deserve elevated weighting.
- [ ] **Owen Caissie 74% arsenal coverage:** Caissie's coverage of May's pitch mix is an advanced metric not currently in our model. Need to incorporate "arsenal coverage" data from FanGraphs/Statcast as a prop-specific metric. When coverage > 65%, flag as premium prop opportunity.

---

### GAME 13: ATH Athletics @ LAA Angels — 9:38 PM ET
**Venue:** Sutter Health Park, Sacramento (outdoor)

#### Model inputs:
| Factor | ATH | LAA |
|--------|-----|-----|
| Starter | Ginn (5-4, 3.16 ERA) | Ureña (5-5, 2.41 ERA) |
| Team record | 39-42 | 34-48 |
| Gelof | OUT (10-day IL, hand contusion) | — |
| Ureña ERA | 2.41 ← excellent for 22-year-old | — |
| Weather | ~70°F, evening conditions | — |

#### BvP: Not pulled this session.

#### Model assessment:
- **Win probability:** ATH 52%, LAA 48%
- **Market implied:** ~50/50
- **Edge:** Minimal — no play
- **Key note:** Ureña's 2.41 ERA is being undervalued. LAA at 34-48 means market discounts him.

#### Model improvement triggers:
- [ ] **Young ace discount:** Ureña (22 years old, 2.41 ERA) is being systematically underpriced because his team is terrible. Need a "starter quality vs team quality" decoupling — a pitcher's ERA should be evaluated independently of his team's record when pricing.
- [ ] **Gelof IL impact:** Zack Gelof on 10-day IL removed ATH's hottest bat (was on 24-game hitting streak before injury). Major lineup downgrade not fully captured in our model. Need same-day "key player absent" check as standard protocol.

---

### GAME 14: LAD Dodgers @ SDP Padres — 9:45 PM ET
**Venue:** Petco Park, San Diego (outdoor — marine layer)
**Apple TV Friday Night Baseball**

#### Model inputs:
| Factor | LAD | SDP |
|--------|-----|-----|
| Starter | Sasaki (3-4, 4.76 ERA) | Buehler (4-3, 3.96 ERA) |
| Team record | 52-29 | 42-37 |
| Sasaki ATS | 4-9 in his starts ← very poor | — |
| Buehler ATS | 11-4 in his starts ← excellent | — |
| Padres ATS | 44-35 overall (56%) | — |
| Ohtani | 7 HR in last 15 games, 12-game hit streak | — |
| Weather | ~68°F, marine layer — pitcher-friendly | — |
| IL (SDP) | Giolito (15-day, elbow), Musgrove (TJS) | — |
| Public betting | High LAD action due to Apple TV exposure | — |

#### BvP: Not pulled this session.

#### Market:
- LAD: -148/-156 | SDP: +126/+129
- O/U: 7.5/8

#### Model assessment:
- **Win probability:** LAD 60%, SDP 40%
- **Market implied:** LAD 60%, SDP 42%
- **Edge:** Minimal on ML. Run line value: SDP +1.5 (-136)
- **Pick:** SDP +1.5 run line (value play based on ATS trends)
- **Public money fade opportunity:** Apple TV game draws heavy LAD public money — sharp fade opportunity

#### Model improvement triggers:
- [ ] **Public betting exposure game:** National TV games (Apple TV Friday Night Baseball, ESPN Sunday Night, FOX Saturday) attract disproportionate public money on the marquee team. Need a "public money discount" for favorite team on national broadcast — fade the over-bet favorite, take run line value.
- [ ] **Sasaki ATS anomaly:** Team going 4-9 ATS when their best pitcher starts is a significant systematic inefficiency. Despite LAD's dominant record (52-29), Sasaki's starts consistently underperform spread expectations. Track: is this specific to Sasaki or LAD in general?
- [ ] **Marine layer O/U impact:** Petco's marine layer consistently suppresses fly ball distance and run scoring. Formalize: Petco night games = subtract 0.5-0.75 runs from O/U expectation vs neutral park.
- [ ] **Buehler ATS record:** 11-4 ATS as a starter is exceptional. "Starter ATS record" should be a formal model layer (same recommendation as Game 6 — Cantillo).

---

### GAME 15: ATL Braves @ SF Giants — 10:15 PM ET
**Venue:** Oracle Park, San Francisco (outdoor)

#### Model inputs:
| Factor | ATL | SF |
|--------|-----|-----|
| Starter | R. López (3-1, 3.50 ERA) | T. McDonald (2-5) — confirmed by FanDuel |
| Team record | 48-31 | 33-47 |
| Matt Olson | MVP-caliber season, 39 XBH | — |
| Weather | 61°F, 8mph wind OUT to CF | — |
| Giants IL | Winn (elbow, IL) | — |
| Lopez ATS | 3-2 in his starts | — |
| McDonald vs dogs | Giants 4-5 in his underdog starts | — |
| O/U | 7.5 (over -122) | — |

#### BvP: Not pulled this session (Giants page not scraped).

#### Market:
- ATL: -122 | SF: +104
- O/U: 7.5 (over -122)

#### Model assessment:
- **Win probability:** ATL 68%, SF 32%
- **Market implied:** ATL 55%, SF 47%
- **Edge:** ATL +13% — but market price (-122) doesn't reflect this well
- **Pick:** ATL -122 (medium conviction) + Over 7.5 lean (wind out to CF)
- **Note:** BvP not pulled — McDonald confirmed by FanDuel, not BR. Need to verify.

#### Model improvement triggers:
- [ ] **Multiple source starter confirmation:** BR showed no Giants starter, FanDuel showed McDonald. Same-day sources should always take priority, and an explicit "starter confirmed" checkbox should be required before finalizing any pick.
- [ ] **O/U with small totals + wind out:** When total is 7.5 or below AND wind is blowing out >8mph, over becomes more attractive. Wind out at Oracle + ATL's power lineup (Olson, etc.) = run environment better than total suggests.
- [ ] **Large record gap pricing:** ATL 48-31 vs SF 33-47 is a 15-game gap. When record differential exceeds 12+ games, market tends to undercharge the better team on ML (market regression to mean). ATL should be closer to -160/-170 based purely on record differential.

---

## CROSS-GAME MODEL IMPROVEMENTS SUMMARY

### Priority 1 (Fix immediately — caused wrong picks):
1. **BvP MUST be Step 1, not Step 7.** Run BvP before building win probabilities. The NYY/BOS under was flagged incorrectly because BvP wasn't run until after. HOU's conviction was also miscalibrated.
2. **Same-day starter confirmation required.** ESPN/MLB.com take priority over Baseball Reference for day-of starter. Build explicit source hierarchy: MLB.com > ESPN > FanDuel > BR.
3. **Rain flag protocol.** If ANY source flags rain, mark pick as CONDITIONAL regardless of precipitation percentage shown elsewhere. WSN/BAL showed 1% on RotoWire but ESPN flagged it — discrepancy should trigger CONDITIONAL status.

### Priority 2 (Add to model — missed value):
4. **IL severity score.** 60-day=3pts, 15-day=2pts, 10-day=1pt, DTD=0.5pt. Total score penalizes team offense/defense proportionally.
5. **Starter ATS record.** Cantillo 12-4, Buehler 11-4, Skenes 5-11 — these are significant signals. Add as formal model input.
6. **Pitcher vs specific team ERA.** Warren's 9.42 ERA vs BOS and Rogers' 5.09 ERA vs WSN should be weighted alongside overall ERA.
7. **Pitcher HR/9 rate.** For prop assessments, HR/9 should be a primary input. Sandlin at 2.70 HR/9 with Caglianone on a 6-in-7 HR streak = auto-trigger.
8. **Park multipliers.** Coors: +1.5 runs. Petco marine layer: -0.5 runs. Fenway short porch: +0.3 runs. Nationals Park heat: +0.5 runs. Formalize these.

### Priority 3 (Refine — improve calibration):
9. **BvP minimum PA threshold.** Weight BvP only if 4+ PA. Flag but don't weight if <4 PA. Separate "confirmed ownership" from "small sample noise."
10. **National TV public money discount.** Apple TV, ESPN, FOX games attract 15-25% more public money on marquee team. Counter-fade the over-bet favorite by 3-5%.
11. **Small-market ace discount.** Meyer at +102 with 8-0/2.80 ERA is a pricing anomaly. Track to confirm market systematically underprices small-market elite starters.
12. **Team road record weighting.** MIA's 28-17 road record deserves more weight than overall 42-39. Road record (when sample > 25 games) should be primary over total record for road teams.
13. **xERA vs ERA gap flag.** When xERA exceeds ERA by 1.5+, flag pitcher as overperformer due for regression. Bradley (4.11 ERA, 6.19 xERA) is a prime example.
14. **"Never faced" opponent signal.** When pitcher has never faced tonight's opponent as starter, model should slightly favor the batting team (unknown = regression to mean + element of surprise). Estimate: +2-3%.
15. **Key player returning from IL.** De La Cruz returning, Seager returning — first game back from injury should add 2-4% to team win probability (player motivation + lineup upgrade, but not 100% full strength).

### Priority 4 (New data sources to integrate):
16. **FanGraphs arsenal coverage data.** Caissie's 74% vs May caught by Covers.com prop analysis. This metric should be a standard HR prop input.
17. **Umpire data.** Not used this session at all. Umpire K rates and run environment tendencies should be incorporated — especially for over/under bets.
18. **Lineup confirmation window.** Set a formal T-2hr check before each game. Review confirmed lineups and flag any changes from initial assessment. Schwarber's potential scratch, Seager's return — these emerged same-day.
19. **Bullpen usage/fatigue.** Not modeled at all. Teams pitching on short rest in bullpen (back-to-back high-leverage games) should have adjusted run prevention numbers.
20. **Starter pitch count recent starts.** Arrighetti threw 101 pitches his last start 6 days ago. Is he stretched out or being managed carefully? This affects expected innings and bullpen exposure.

---

## OUTCOME TRACKING TEMPLATE

| Pick | Type | Line | My % | Mkt % | Result | Correct? |
|------|------|------|------|--------|--------|---------|
| WSN +120 | ML | +120 | 61% | 45% | TBD | TBD |
| MIA +102 | ML | +102 | 58% | 45% | TBD | TBD |
| HOU -102 | ML | -102 | 52% | 50% | TBD | TBD |
| NYY -110 | ML | -110 | 60% | 52% | TBD | TBD |
| PIT -190 FADE | ML fade | -190 | 60% | 66% | TBD | TBD |
| WSN/BAL Over 9 | O/U | Over 9 | — | — | TBD | TBD |
| COL/MIN Over 8.5 | O/U | Over 8.5 | — | — | TBD | TBD |
| NYY/BOS Under 8 (REMOVED) | O/U ghost | Under 8 | — | — | TBD | Was pull correct? |
| CJ Abrams HR | Prop | ~+280 | — | — | TBD | TBD |
| Caglianone HR | Prop | +400 | — | — | TBD | TBD |
| Goldschmidt HR | Prop | +446 | — | — | TBD | TBD |
| Christian Walker HR | Prop | ~+280 | — | — | TBD | TBD |
| TJ Rumfield HR | Prop | ~+320 | — | — | TBD | TBD |
| Parlay A (WSN+MIA+HOU) | Parlay | ~+550 | — | — | TBD | TBD |
| Parlay B (Caglianone+Goldy+Walker HR) | Parlay | ~+4000 | — | — | TBD | TBD |

---

## QUESTIONS TO ANSWER JUNE 27

1. What was the overall win rate? (ML picks, props, O/U separately)
2. Did BvP-driven decisions improve outcomes? (HOU downgrade, Under removal)
3. Did the rain flag on WSN/BAL materialize? Was the pick manageable?
4. Which of the 20 model improvements would have changed the most outcomes?
5. Are there new patterns from June 26 results that suggest additional model inputs?
6. What was the hit rate on HR props at +280-+446? Is that price range efficient?
7. Did the "Seager returning" signal help TEX? (Validate returning player impact)
8. Did Suzuki's HR streak end vs Misiorowski? (Validate elite K pitcher streak fade)
9. Did public money inflate LAD price and create SDP value? (Validate national TV fade)
10. Which source (ESPN vs BR) was correct on STL starter (May vs McGreevy)?

