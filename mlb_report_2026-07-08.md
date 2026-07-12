# MLB Model Report — Wednesday, July 8, 2026

*Automated nightly run. **No independent model feed was reachable tonight** (FanDuel Research, numberFire and the DraftKings sportsbook were all blocked; ESPN/Covers served stale July-7 caches). Live moneylines and probable starters were pulled from the **RotoWire live board**; with no model win-probability feed, each game is priced to its **de-vigged fair line** — zero constructed edge by design. Sizing still runs through the week-1-calibrated `mlb_edge` ladder.*

## Bottom line

**No qualifying play tonight — 0 units staked.** Because every game was priced to its own fair (de-vigged) market number, no side shows a positive edge, so nothing clears the calibrated thresholds (favorites ≥6%, underdogs ≥2%). This is a data-limited pass, not a read that the 14 games are all efficient — it reflects that no independent probability model could be attached in this environment. A Windows-side data pull + trained-model run would restore real edges.

---

## Yesterday (July 7) — no action

July 7 was a disciplined no-play (no qualifying edges on the 7 modeled games), so there was nothing to grade. **Season record unchanged: 19W-13L, +2.749u** (through July 6).

*DB note: `data/mlb.db` was again found malformed on this run (recurring sandbox/FUSE issue). Rebuilt from `picks_history_backup.csv` via the documented recipe — fresh schema + 32 graded picks rebuilt in local storage, integrity verified `ok`, copied back over the mount, stale journal truncated.*

---

## Today's slate — 14 games (Phillies @ Reds unposted)

Odds are the RotoWire best-of-book live board; "Fair%" is the de-vigged two-sided market (= the model tonight). Edge is ~0 by construction on both sides, hence every game is a pass.

| Game (Away @ Home) | Starters | Away ML / Home ML | Fair% (favorite) | Call |
|---|---|---|---|---|
| Blue Jays @ Giants | Cease / Webb | -109 / -102 | ~50/50 (TOR 50.8%) | Pick'em — pass |
| Cubs @ Orioles | Rea / Kremer | +111 / -124 | BAL 53.9% | Fair — pass |
| Athletics @ Tigers | Springs / Melton | +138 / -154 | DET 59.1% | Fair — pass |
| Yankees @ Rays | Cole / McClanahan | +110 / -122 | TBR 53.6% | Fair — pass |
| Mariners @ Marlins | Kirby / Phillips | -127 / +118 | SEA 55.0% | Fair — pass |
| Braves @ Pirates | Holmes / Jones | +105 / -116 | PIT 52.4% | Fair — pass |
| Astros @ Nationals | Arrighetti / Griffin | +118 / -131 | WSN 55.3% | Fair — pass |
| Royals @ Mets | Kolek / Scott | +124 / -146 | NYM 57.1% | Fair — pass |
| Red Sox @ White Sox | Bennett / Martin | +107 / -119 | CHW 52.9% | Fair — pass |
| Guardians @ Twins | Cecconi / Prielipp | +117 / -130 | MIN 55.1% | Fair — pass |
| Brewers @ Cardinals | Harrison / McGreevy | -134 / +123 | MIL 56.1% | Fair — pass |
| Angels @ Rangers | Ureña / Gore | +140 / -153 | TEX 59.2% | Fair — pass |
| Rockies @ Dodgers | Feltner / Sasaki | +205 / -225 | LAD 67.9% | Chalk — pass |
| Diamondbacks @ Padres | Cabrera / King | +125 / -139 | SDP 56.7% | Fair — pass |

**Phillies @ Reds:** no moneyline was posted on the live board at pull time (probable-starter uncertainty — Keller/King vs Burns). Left off the actionable slate rather than priced on a guess.

## Monitors (no bet — context only)

- **Marquee arms, fairly priced:** Gerrit Cole (@TBR), Logan Webb (vs TOR), MacKenzie Gore (vs LAA), Roki Sasaki (vs COL) and Michael King (vs ARI) are the names to watch. Without a model overlay there's no basis to call the market wrong on any of them.
- **Heavy chalk:** Dodgers -225 (Sasaki vs a Feltner/Rockies road team) and Rangers -153 (Gore) look like correct favorites; no stated edge either way.

## Value picks

**None.** No side clears the calibrated edge thresholds under market-devig pricing.

**Parlay:** none — no qualifying legs.

---

## Data & environment notes

- **Model feed unavailable:** FanDuel Research, numberFire and DraftKings sportsbook were all blocked this run; ESPN `/mlb/odds` and Covers returned stale July-7 slates. The RotoWire live board rendered the real July-8 games (moneylines + starters), and FanGraphs supplied the probables grid.
- **Starter conflicts across sources** on four teams — Mariners (Kirby vs Woo), Marlins (Phillips vs Junk), Cardinals (McGreevy vs Pallante), Phillies (King vs Keller). The RotoWire live board (same source as the odds) was used where it disagreed.
- **Model still on formula/market fallback** — XGBoost and `pybaseball` are unavailable in the sandbox (disk-space constrained); a Windows-side data pull + retrain is required to activate the trained model and produce true per-game probabilities.
- No altitude game on the card (Colorado plays at Dodger Stadium), so no park-variance discount was triggered; live weather APIs remain blocked.

*Dashboard: `mlb_dashboard_2026-07-08.html` → pushed to https://bbitsky.github.io/MLB-Daily/*
