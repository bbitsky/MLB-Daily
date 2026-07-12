# MLB Model Report — Sunday, July 12, 2026

## ⚠️ NO PLAYS TODAY — picks withdrawn after review

A full re-verification of today's slate found that the overnight model run produced **corrupted numberFire win-probabilities**, so the picks it generated were phantom edges, not real ones. They have been withdrawn. Do not bet them.

**The proof:** in 4 games the model's numberFire number contradicted the market by 8–24 points — and those 4 were exactly the strongest "picks":

| Game | Market (fav) | Model said | Verdict |
|---|---|---|---|
| Arizona @ LA Dodgers | LAD ~-300 (AZ 28%) | AZ **52%** | impossible — AZ is a +240 dog |
| Cubs @ Reds | Cubs -135 (Cubs 55%) | Cubs **44%** | inverted — drove a phantom "Reds +115" edge |
| Braves @ Cardinals | ATL -140 (ATL 56%) | ATL **48%** | inverted — drove a phantom "Cardinals" edge |
| Yankees @ Nationals | ~pick'em | (line was also wrong) | see below |

This is the same corruption that produced **yesterday's 0-4**. Today's July-12 numberFire values could not be independently re-pulled to rebuild the edges cleanly, so there is **no defensible value pick today**. The disciplined move is no bet.

## Data errors corrected on the dashboard (slate is now accurate for reference)

- **Yankees @ Nationals:** the build had NYY -190 / WSH +160. That's wrong — it's essentially a **pick'em** (NYY ~-115 / WSH ~-105). Cavalli (sharp) vs Warren (scuffling) at home. *(Your book showing WSH ~-116 was right; my +160 was stale from the July 11 game.)*
- **Blue Jays @ Padres:** odds were **side-swapped** — San Diego is the **-125 favorite**, Toronto the **+105 dog** (build had it reversed).
- **Totals fixed:** Brewers@Pirates 7.5, Guardians@Marlins 8.5, Mariners@Rays 7.5 (and TB is ~-130, not -145).
- **Diamondbacks +240** — the line is real but book-dependent (LAD anywhere -205 to -322); regardless, the model's 52% on Arizona is not.
- **All 15 starting pitchers verified correct.**

## Record (accurate)

- Yesterday (July 11): **0-4, -2.00u** (all four dogs lost; the Cardinals game had been mis-graded as a win and is corrected).
- Season: **23-20 (53.5%), +1.66u**.

## Root cause / fix needed

The nightly build's numberFire feed is unreliable — it inverts or mislabels the away/home win probabilities, so favorites look weak and plus-money dogs look strong, manufacturing edges that don't exist. Until that feed is fixed and validated (each game's numberFire number should have the favorite above 50%), the model's "value picks" cannot be trusted. Recommended guardrail: in the build, **reject any game where the numberFire side disagrees with the no-vig market by more than ~10 points** (flag for manual review instead of auto-betting).

*Model on ERA-formula fallback (trained XGBoost unavailable in sandbox); live odds pages don't render here, so lines are from text sources — confirm at your book.*
