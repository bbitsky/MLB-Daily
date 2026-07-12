# MLB Model Report — Friday, July 10, 2026

*Automated nightly run. All win probabilities use the numberFire independent overlay where reachable; games without it fall back to no-vig market and are monitor-only (cannot mint a pick). Odds are consensus/Action Network as of the overnight pull and will move — confirm at your book before betting.*

---

## ⚠️ Run health / caveats (read first)

- **Yesterday's results (July 9) were NOT logged.** The synced `data/mlb.db` is a truncated 53 KB husk (its own header expects ~9.4 MB / 2,285 pages), so every DB read fails the integrity check. The live DB lives on your Windows LocalAppData and isn't reachable from the sandbox. Result-grading, season P/L, and CLV are stale until the DB is repaired on the Windows side (`python repair_mlb_db.py`, or re-copy the live LocalAppData DB into `data/`).
- **numberFire access was indirect.** The FanDuel/odds index pages are JavaScript-rendered and returned empty, and no browser was connected for this autonomous run. Independent win probabilities were recovered from search snippets for 6–7 games only; the rest fell back to no-vig market. A couple of nF values are *derived from the complementary (home) number*. **Treat today's edges as lower-confidence than a normal live run.**
- **The single HIGH pick (Rangers) hinges on a derived/unverified numberFire value that disagrees with the market by ~10 points.** See the pick note. Verify against a live numberFire read before staking.

---

## ✅ Midday re-verification (lines + starters re-pulled)

Re-checked every game against current per-game sources. **Both picks stand and their starters are confirmed** — Brown/Quantrill (Rangers) and Sale/Leahy (Cardinals). Corrections found elsewhere in the slate:

- **POSTPONED — Brewers @ Pirates** rained out; made up as a doubleheader **Sat 7/11**. (Was a no-play anyway.)
- **Athletics starter: Jacob Lopez, not Aaron Civale** (my error — Civale is not starting). No-play game.
- **Nationals: Carson Palmquist is the listed opener** (Littell works bulk behind him). No-play game.
- **Totals corrected:** D-backs@Dodgers 7.0→**8.5**; Astros@Rangers 8.5→**8.0**; Blue Jays@Padres 8.0→**7.5**; Angels@Twins 8.5→**9.0**.
- **Phillies @ Tigers now has a line:** PHI +103 / DET −122, total 8.5 (was unposted; still a no-play).
- **Minor line drift (shop the number):** Mets −127 (was −134); Giants −156/−160 (was −166); Yankees −160 (−167); Mets/Cardinals/Rangers picks moved ≤1–2 cents. Books disagree most on Mets and Giants.

Bottom line: none of this changes the two bets. Rangers **+118/+120** and Cardinals **+139** are still live.

---

## Value picks (ranked by edge)

| Rank | Pick | Odds | Model prob | Implied | Edge | Conviction | Stake |
|---|---|---|---|---|---|---|---|
| 1 | **Texas Rangers** ML (vs HOU) | +118 | 56.2% (nF) | 45.9% | **+10.3%** | HIGH | 0.75u |
| 2 | **St. Louis Cardinals** ML (vs ATL) | +138 | 46.7% (nF) | 42.0% | **+4.7%** | MEDIUM | 0.50u |

**Pick 1 — Rangers +118 vs Astros (Quantrill 3.35 vs H. Brown 3.38).** numberFire has Houston at just 43.8% despite the market pricing them −138 favorites; that ~10-point gap is what drives the HIGH tag. **Data-quality flag:** this nF figure was *derived* from the complementary number and could not be confirmed directly. A gap this large against an efficient market is as often a stale/mis-scraped number as a real edge. Recommend confirming the live numberFire (or a second model) before betting; if it can't be confirmed, downgrade to a monitor.

**Pick 2 — Cardinals +138 vs Braves (Sale 2.27 vs Leahy 3.86).** numberFire gives Atlanta 53.3% vs the market's implied 62.1% on Sale — it thinks the market is overpaying for the ace. Modest, cleaner signal; standard MEDIUM sizing.

**Parlay:** none recommended. Only one HIGH-tier leg, and it carries a data-quality flag — not parlay material.

---

## Full slate (15 games)

| Away (SP, ERA) | Home (SP, ERA) | Away ML | Home ML | O/U | Model (away) | Note |
|---|---|---|---|---|---|---|
| Red Sox — S. Gray 2.61 | Mets — N. McLean 3.78 | +113 | −134 | 7.5 | 45.0% (no-vig) | monitor; Gray 10-1 |
| Athletics — A. Civale 5.10 | White Sox — S. Burke 3.56 | +140 | −170 | 9.0 | 39.8% (no-vig) | monitor |
| Royals — L. Avila 5.40 | Orioles — B. Young 3.38 | +125 | −151 | 9.5 | 42.4% (no-vig) | monitor |
| Brewers — B. Sproat 5.28 | Pirates — B. Ashcraft 3.24 | +108 | −126 | 8.5 | 43.8% (nF) | nF ≈ market, no edge |
| Rockies — T. Gordon 6.69 | Giants — R. Ray 3.45 | +140 | −166 | 8.5 | 40.0% (no-vig) | monitor |
| Diamondbacks — E. Rodriguez 2.21 | Dodgers — S. Ohtani 1.79 | +210 | −255 | 7.0* | 28.3% (nF) | nF likes LAD, sub-threshold |
| **Braves — C. Sale 2.27** | **Cardinals — K. Leahy 3.86** | −164 | **+138** | 8.0 | 53.3% (nF) | ✅ **PICK: STL 0.5u** |
| Cubs — S. Imanaga 4.28 | Reds — H. Greene 21.60† | −113 | −106 | 9.5 | 51.6% (no-vig) | monitor |
| Yankees — R. Weathers 4.08 | Nationals — Z. Littell 5.02 | −167 | +137 | 10.0 | 62.5% (no-vig) | monitor |
| Guardians — P. Messick 2.80 | Marlins — S. Alcantara 4.00 | +100 | −118 | 7.5 | 40.1% (nF) | nF likes MIA, sub-threshold |
| **Astros — H. Brown 3.38** | **Rangers — C. Quantrill 3.35** | −138 | **+118** | 8.5 | 43.8% (nF) | ✅ **PICK: TEX 0.75u ⚠️** |
| Blue Jays — S. Bieber 9.00† | Padres — JP Sears 6.97 | −104 | −112 | 8.0 | 48.1% (nF) | pick-em, no edge |
| Mariners — L. Castillo 4.79 | Rays — N. Martinez 2.61 | −110 | −110 | 8.0 | 50.0% (no-vig) | monitor |
| Angels — G. Rodriguez 8.06 | Twins — Z. Matthews 4.43 | +110 | −130 | 8.5 | 39.3% (nF) | nF likes MIN, sub-threshold |
| Phillies — A. Nola 6.04 | Tigers — J. Flaherty 4.60 | NA | NA | NA | — | no posted line; monitor |

\* Diamondbacks@Dodgers total not posted at pull time — 7.0 is an estimate for display only.
† Greene (21.60, 3.1 IP) and Bieber (9.00, 13 IP) ERAs are tiny-sample returns from injury; not reliable.

**Notes on the "near-miss" nF games:** the overlay also liked Marlins (−118, +5.8% raw), Twins (−130, +4.2% raw) and Dodgers (−255, small) on the home side, but after the mlb_edge favorite penalty and conviction recalibration none cleared the betting threshold — monitors only.

---

## Method / provenance

Probable starters and ERAs from the FanGraphs July 10 SP chart (authoritative). Moneylines/totals from Action Network per-game pages plus book snippets. Independent probabilities from numberFire (via FanDuel Research) where reachable. Edges = numberFire probability − market implied, park-adjusted; sizing via the calibrated `mlb_edge` conviction ladder. Picks frozen to `picks_frozen_2026-07-10.json` (14 games) and will not be recomputed on dashboard rebuilds. DB logging was skipped this run due to the corrupt husk.

Sources: [FanGraphs SP chart 7/10](https://fantasy.fangraphs.com/starting-pitcher-chart-july-10th-2026/) · [FanDuel Research 7/10](https://www.fanduel.com/research/mlb-betting-odds-07-10-2026) · [Action Network — Red Sox@Mets](https://www.actionnetwork.com/mlb-game/red-sox-mets-score-odds-july-10-2026/291716)


---

## Why / Why-Not Bet — 2026-07-10

**Texas Rangers +118 vs Houston Astros — HIGH (0.75u)**  ·  model 56.2% vs 45.9% implied · edge +10.3%

*Why:* numberFire has Texas at 56.2% while the board makes them a +118 home dog — a 10.3-pt disagreement, and the entire case. The arms are a wash (Quantrill 3.35 vs Brown 3.38), so there's nothing in the matchup that justifies pricing Houston as a −138 road favorite; you're getting plus-money on the side the model prefers. *Why not / sizing:* that nF number was derived from the complementary figure and couldn't be confirmed against a live read — a 10-point gap versus an efficient market is as often a bad scrape as a real edge — so it's capped at 0.75u, and Houston is the better roster on paper. Confirm the live numberFire before firing; if you can't, drop it to a monitor.

**St. Louis Cardinals +138 vs Atlanta Braves — MEDIUM (0.5u)**  ·  model 46.7% vs 42.0% implied · edge +4.7%

*Why:* the market is paying the Chris Sale name tax — −164 implies 62.1%, but numberFire only gives Atlanta 53.3%, leaving the Cardinals a +138 dog with a real overlay at home. *Why not / sizing:* Sale (2.27) genuinely is the sharper arm and Leahy (3.86) is a clear step down, so the edge is modest and single-source — 0.5u, not more.

**Everything else got filtered out — with the actual reason:**

- **Milwaukee Brewers @ Pittsburgh Pirates** (CHALK) — Model and market agree: nF Pirates 56.2% ≈ −126 implied (55.8%). Ashcraft (3.24) is the better arm, but there's no gap to bet. Parlay filler at most. [B. Sproat 5.28 vs B. Ashcraft 3.24]
- **Cleveland Guardians @ Miami Marlins** (NEAR-MISS) — The cleanest one that got away: nF actually likes Miami (~+5.8% raw on −118), but Messick (2.80) is the sharper arm for Cleveland and the favorite penalty knocks Miami below the bet line. Worth watching live. [P. Messick 2.80 vs S. Alcantara 4.00]
- **Los Angeles Angels @ Minnesota Twins** (LEAN, no bet) — nF leans Minnesota and G. Rodriguez (8.06) is a real problem for the Angels, but MIN −130 after the favorite penalty is sub-threshold. [G. Rodriguez 8.06 vs Z. Matthews 4.43]
- **Arizona Diamondbacks @ Los Angeles Dodgers** (NO VALUE) — Ace duel, Ohtani 1.79 vs E-Rod 2.21. nF tilts slightly to LA but they're −255; there's no plus-value on a 72% favorite. [E. Rodriguez 2.21 vs S. Ohtani 1.79]
- **Chicago Cubs @ Cincinnati Reds** (NOISE) — Greene's 21.60 is a 3.1-inning return-from-injury mirage, so the model read here is unreliable and the no-vig line is near pick-em. Pass on the noise. [S. Imanaga 4.28 vs H. Greene 21.60†]
- **Toronto Blue Jays @ San Diego Padres** (COIN FLIP) — Two shaky arms — Bieber 9.00 (13 IP back from injury) vs Sears 6.97 — and a −104/−112 pick-em with nF ~48%. No edge, expect variance. [S. Bieber 9.00† vs JP Sears 6.97]
- **Colorado Rockies @ San Francisco Giants** (RIGHT SIDE, NO PRICE) — Ray (3.45) is far the better arm and the Giants are the side, but there's no independent overlay here and −166 leaves no value. [T. Gordon 6.69 vs R. Ray 3.45]
- **Boston Red Sox @ New York Mets** (MARKET'S AHEAD) — Sonny Gray (2.61, 10-1) is the class of the card vs McLean (3.78), but BOS is only +113 — the market already respects him — and there's no overlay. Lindor questionable (hand) for NYM. Monitor. [S. Gray 2.61 vs N. McLean 3.78]
- **New York Yankees @ Washington Nationals** (PRICED IN) — Weathers (4.08) over Littell (5.02) leans NYY, but −167 with no independent read is already steep. Monitor. [R. Weathers 4.08 vs Z. Littell 5.02]
- **Kansas City Royals @ Baltimore Orioles** (FAIR) — Young (3.38) ≫ Avila (5.40); BAL −151 is a fair price with no model overlay to beat it. [L. Avila 5.40 vs B. Young 3.38]
- **Athletics @ Chicago White Sox** (FAIR) — Burke (3.56) > Civale (5.10); CWS −170 is priced right, no independent edge. [A. Civale 5.10 vs S. Burke 3.56]
- **Seattle Mariners @ Tampa Bay Rays** (PICK-EM) — N. Martinez (2.61) is the better arm at home, but it's a dead −110/−110 with no overlay to break the tie. [L. Castillo 4.79 vs N. Martinez 2.61]
- **Philadelphia Phillies @ Detroit Tigers** (NO LINE) — No moneyline posted at pull time, so it can't be priced. Monitor only. [A. Nola 6.04 vs J. Flaherty 4.60]

**Parlay:** none recommended. Only one HIGH leg, and it carries a data-quality flag — not parlay material. (Ignore any auto-generated "combo" count; those are unqualified.)

**Caveats:** Model on the ERA-differential + win% formula fallback (trained XGBoost unavailable in the sandbox). Edges lean on the numberFire overlay, which was only reachable for ~7 games — the rest are no-vig monitors. Lines move; confirm the price is still live before staking.
