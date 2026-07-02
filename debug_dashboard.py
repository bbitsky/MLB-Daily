"""Quick diagnostic: shows what data the model is working with today."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from mlb_data import fetch_today_odds, parse_odds_event, fetch_today_game_data, fetch_standings

LEAGUE_AVG_ERA = 4.50

def ml_to_prob(ml):
    if ml is None: return 0.5
    if ml < 0: return (-ml) / (-ml + 100)
    return 100 / (ml + 100)

def simple_prob(away_era, home_era, away_wp, home_wp, pf):
    era_adj = (home_era - away_era) * 0.025
    wp_adj  = (away_wp - home_wp) * 0.15
    pf_adj  = (pf - 1.0) * 0.03
    return max(0.32, min(0.68, 0.47 + era_adj + wp_adj + pf_adj))

print("=" * 70)
print("STEP 1: Odds API games")
print("=" * 70)
raw = fetch_today_odds()
odds_games = [parse_odds_event(e) for e in raw]
print(f"Found {len(odds_games)} games from Odds API:")
for g in odds_games:
    print(f"  '{g['away_team']}' @ '{g['home_team']}'  ML:{g['away_ml']}/{g['home_ml']}")

print()
print("=" * 70)
print("STEP 2: MLB Stats API game data")
print("=" * 70)
from datetime import date
today = date.today().isoformat()
mlb_games = fetch_today_game_data(today)
print(f"Found {len(mlb_games)} games from MLB API:")
for g in mlb_games:
    print(f"  '{g['away_team']}' @ '{g['home_team']}'")
    print(f"    Away SP: {g['away_starter']}  ERA:{g['away_era']:.2f}  GS:{g['away_gs']}  WP:{g['away_win_pct']:.3f}  Rest:{g['away_rest']}d")
    print(f"    Home SP: {g['home_starter']}  ERA:{g['home_era']:.2f}  GS:{g['home_gs']}  WP:{g['home_win_pct']:.3f}  Rest:{g['home_rest']}d")
    print(f"    Venue: {g['venue']}  PF:{g['park_factor']:.2f}")

print()
print("=" * 70)
print("STEP 3: Merge + probabilities")
print("=" * 70)
game_lookup = {(g["away_team"], g["home_team"]): g for g in mlb_games}
for og in odds_games:
    away, home = og["away_team"], og["home_team"]
    auto = game_lookup.get((away, home), {})
    matched = bool(auto)

    away_era  = auto.get("away_era",    LEAGUE_AVG_ERA)
    home_era  = auto.get("home_era",    LEAGUE_AVG_ERA)
    away_wp   = auto.get("away_win_pct", 0.500)
    home_wp   = auto.get("home_win_pct", 0.500)
    pf        = auto.get("park_factor",  1.00)

    base      = simple_prob(away_era, home_era, away_wp, home_wp, pf)
    home_prob = 1 - base

    away_impl = ml_to_prob(og["away_ml"])
    home_impl = ml_to_prob(og["home_ml"])
    away_edge = base - away_impl
    home_edge = home_prob - home_impl

    print(f"\n  {away} @ {home}  [MLB data: {'MATCHED' if matched else 'NO MATCH - using defaults'}]")
    print(f"    Away ERA:{away_era:.2f}  Home ERA:{home_era:.2f}  Away WP:{away_wp:.3f}  Home WP:{home_wp:.3f}  PF:{pf:.2f}")
    print(f"    Model away:{base:.1%}  home:{home_prob:.1%}")
    print(f"    Market away:{away_impl:.1%} ({og['away_ml']})  home:{home_impl:.1%} ({og['home_ml']})")
    print(f"    Edge  away:{away_edge:+.1%}  home:{home_edge:+.1%}", end="")
    best = max(away_edge, home_edge)
    if best >= 0.08:   print("  --> HIGH")
    elif best >= 0.06: print("  --> MED-HIGH")
    elif best >= 0.05: print("  --> MEDIUM")
    elif best >= 0.02: print("  --> LEAN")
    else:              print("  --> NO PLAY")
