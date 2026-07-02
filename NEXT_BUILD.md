# Next Build: In-Game Live Odds Model

## Concept
A separate system that runs AFTER first pitch to find live betting edges.
Completely independent from the pre-game model.

## Data sources needed
- The Odds API live endpoint: `/v4/sports/baseball_mlb/odds/?markets=h2h&live=true`
- MLB Stats API live boxscore: `/game/{gamePk}/linescore` + `/game/{gamePk}/boxscore`
  - Current inning, outs, base runners, run differential
  - Starter status (still in game / pulled)
  - Hitter performance in this game (PA, hits, K, BB today)
- Bullpen state per team: who has already pitched today, how many pitches/innings

## Model inputs (in-game features)
- Live moneyline (Odds API)
- Inning + half
- Run differential
- Base-out state (24 states)
- Starter still pitching? + current pitch count
- Bullpen arms used today (rest, effectiveness tier)
- Hitter matchup: batter vs current pitcher hand (live box)
- Team scoring rate last 3 innings vs season avg

## Key differences from pre-game model
- No need for park factor / weather (already in play)
- Leverage = key: inning 7+ with 1-run game is highest leverage
- Recalibrate implied prob from live line and compare to "true" win prob given game state

## Files to create
- `mlb_live.py` — live odds fetcher + boxscore parser
- `mlb_live_model.py` — feature builder + prediction
- `mlb_live_dashboard.py` or add tab to existing dashboard
- Run trigger: every 15-20 min during game windows (6 PM – midnight ET)

## Status
[ ] Not started
