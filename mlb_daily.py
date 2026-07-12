# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

"""
mlb_daily.py -- Daily picks runner for MLB Betting Model v3

Run each morning:
    python mlb_daily.py

What it does:
  1. Pulls today's MLB games + live moneylines from The Odds API
  2. Fetches starting pitcher stats from MLB Stats API
  3. Pulls team records from the local DB (or approximates from season stats)
  4. Runs the trained ML model for win probabilities
  5. Applies v2.1 manual-rule overlays (national TV fade, ump, IL flags, etc.)
  6. Outputs ranked picks with edge, conviction, and unit sizing
  7. Logs picks to the database for results tracking

Usage:
    python mlb_daily.py              # today's picks
    python mlb_daily.py --date 2025-06-27   # picks for a past date (if odds available)
    python mlb_daily.py --log-results       # enter yesterday's results into DB
"""

import sys
import sqlite3
import argparse
from datetime import datetime, date
from pathlib import Path
from itertools import combinations

import pandas as pd
import numpy as np

from mlb_data import (
    fetch_today_odds, parse_odds_event, fetch_game_starters,
    fetch_pitcher_season_stats, fetch_team_record_on_date,
    fetch_today_game_data,
    PARK_FACTORS, DOME_PARKS, DB_PATH, init_db,
    ALL_STAR_BREAK_END,
)
from mlb_train import predict_game, load_model, LEAGUE_AVG_ERA
try:
    import mlb_edge as _EDGE
except Exception as _e:
    _EDGE = None
    print(f'  [warn] mlb_edge unavailable ({_e}); using legacy conviction ladder')


# -------------------------------------------------
# MONEYLINE MATH
# -------------------------------------------------

def ml_to_prob(ml: int) -> float:
    """Convert American moneyline to implied probability (no vig)."""
    if ml >= 0:
        return 100.0 / (ml + 100.0)
    else:
        return abs(ml) / (abs(ml) + 100.0)


def ml_str(ml):
    if ml is None:
        return "N/A"
    return f"+{ml}" if ml > 0 else str(ml)


def prob_to_ml(prob: float) -> int:
    """Convert probability to American moneyline."""
    prob = max(0.01, min(0.99, prob))
    if prob >= 0.5:
        return -round(prob / (1.0 - prob) * 100)
    else:
        return round((1.0 - prob) / prob * 100)


# -------------------------------------------------
# RULE OVERLAYS (v2.1)
# -------------------------------------------------

def apply_rule_overlays(game: dict, base_away_prob: float) -> tuple:
    """Apply manual + auto rule overlays. Returns (adjusted_away_prob, flags)."""
    away_prob = base_away_prob
    flags = []

    # 1. National TV fade (auto-detect + manual override)
    national_tv  = game.get("national_tv", False)
    network      = game.get("national_tv_network", "")
    marquee_side = game.get("marquee_side", None)
    if national_tv:
        adj = 0.03
        away_ml = game.get("away_ml", 0) or 0
        home_ml = game.get("home_ml", 0) or 0
        if home_ml and away_ml and home_ml != away_ml:
            marquee = "home" if home_ml < away_ml else "away"
        else:
            marquee = marquee_side
        if marquee == "home":
            away_prob += adj
            flags.append(f"TV {network}: {game['home_team']} is fav/marquee -> +{adj:.1%} away")
        elif marquee == "away":
            away_prob -= adj
            flags.append(f"TV {network}: {game['away_team']} is fav/marquee -> -{adj:.1%} away")

    # 2. Short rest penalty
    away_rest = game.get("away_rest", 5)
    home_rest = game.get("home_rest", 5)
    if away_rest <= 1:
        away_prob -= 0.03
        flags.append(f"Away starter short rest ({away_rest}d) -> -3%")
    if home_rest <= 1:
        away_prob += 0.03
        flags.append(f"Home starter short rest ({home_rest}d) -> +3% away")

    # 3. Extended rest rust flag
    if away_rest >= 8:
        away_prob -= 0.01
        flags.append(f"Away extended rest ({away_rest}d) rust risk -> -1%")
    if home_rest >= 8:
        away_prob += 0.01
        flags.append(f"Home extended rest ({home_rest}d) rust risk -> +1%")

    # 4. Dome / weather (rain) flag
    rain_flag = game.get("rain_flag", False)
    if rain_flag:
        flags.append("RAIN / weather risk -- confirm game status")

    # 5. Manual overlay flags
    manual_flags = game.get("manual_flags", [])
    flags.extend(manual_flags)

    # 6. LINE OUTLIER flag
    if game.get("line_outlier"):
        gap = game.get("line_outlier_gap", 0)
        flags.append(f"LINE OUTLIER: best line differs from consensus by {gap:.1f}pp -- use consensus")

    away_prob = max(0.20, min(0.80, away_prob))
    return away_prob, flags


# -------------------------------------------------
# CONVICTION + SIZING
# -------------------------------------------------

def get_conviction(edge: float, ml: int = None) -> tuple:
    """Return (conviction_label, units). Week-1 recalibrated via mlb_edge:
    favorites soft-capped/de-sized, dog-ladder top capped at 0.75u. Pass the
    side's moneyline so the favorite penalty applies; legacy ladder is the
    fallback if mlb_edge is unavailable."""
    if _EDGE is not None and ml is not None:
        return _EDGE.conviction(edge, ml)
    if edge >= 0.08:
        return "HIGH", 1.00
    if edge >= 0.06:
        return "MED-HIGH", 0.75
    if edge >= 0.05:
        return "MEDIUM", 0.50
    if edge >= 0.02:
        return "LEAN", 0.25
    return "NO PLAY", 0.0


# -------------------------------------------------
# PARLAY BUILDER
# -------------------------------------------------

def build_parlays(picks, min_leg_prob=0.57, max_legs=3, top_n=8):
    """
    Build high-probability parlays from today's model output.
    Only uses legs where model probability >= min_leg_prob.
    Ranks by expected value.
    """
    legs = []
    for g in picks:
        for side in ("away", "home"):
            prob = g.get(f"{side}_prob", 0)
            ml   = g.get(f"{side}_ml")
            if prob >= min_leg_prob and ml is not None:
                legs.append({
                    "team":    g[f"{side}_team"],
                    "ml":      ml,
                    "prob":    prob,
                    "edge":    g.get(f"{side}_edge", 0),
                    "starter": g.get(f"{side}_starter", "TBD"),
                    "game":    f"{g['away_team']}@{g['home_team']}",
                    "venue":   g.get("venue", ""),
                })

    results = []
    for n in range(2, max_legs + 1):
        for combo in combinations(legs, n):
            # All legs must be from different games
            if len({leg["game"] for leg in combo}) < n:
                continue
            combined_prob = 1.0
            decimal_odds  = 1.0
            for leg in combo:
                combined_prob *= leg["prob"]
                ml = leg["ml"]
                decimal_odds *= (ml / 100.0 + 1.0) if ml >= 0 else (100.0 / abs(ml) + 1.0)
            parlay_ml = (int(round((decimal_odds - 1.0) * 100))
                         if decimal_odds >= 2.0
                         else int(round(-100.0 / (decimal_odds - 1.0))))
            ev = combined_prob * (decimal_odds - 1.0) - (1.0 - combined_prob)
            results.append({
                "legs":          list(combo),
                "n_legs":        n,
                "combined_prob": combined_prob,
                "parlay_ml":     parlay_ml,
                "decimal_odds":  decimal_odds,
                "ev":            ev,
            })

    results.sort(key=lambda x: x["ev"], reverse=True)
    return results[:top_n]


# -------------------------------------------------
# PRINT HELPERS
# -------------------------------------------------

def print_picks_report(picks: list, today: str):
    """Print the daily picks report to stdout."""
    print()
    print("=" * 70)
    print(f"  MLB BETTING MODEL v3 -- Picks for {today}")
    print("=" * 70)

    actionable = [g for g in picks
                  if g.get("away_edge", 0) >= 0.02 or g.get("home_edge", 0) >= 0.02]
    no_play    = [g for g in picks
                  if g.get("away_edge", 0) < 0.02 and g.get("home_edge", 0) < 0.02]

    if not picks:
        print("\n  No games found for today.")
        return

    print(f"\n  {len(picks)} games today  |  {len(actionable)} with model edge\n")

    for g in picks:
        away  = g["away_team"]
        home  = g["home_team"]
        venue = g.get("venue", "")
        pf    = g.get("park_factor", 1.0)
        ou    = g.get("ou_line")
        n_books    = g.get("n_books", 0)
        outlier    = g.get("line_outlier", False)
        away_best  = g.get("away_ml_best")
        home_best  = g.get("home_ml_best")
        away_book  = g.get("away_ml_book", "")
        flags      = g.get("flags", [])

        # Header
        ou_str  = f"  O/U {ou}" if ou else ""
        pf_str  = f"  PF:{pf:.2f}" if venue else ""
        books_str = ""
        if outlier and away_best is not None:
            books_str = f"  [best: {ml_str(away_best)}/{ml_str(home_best)} @ {away_book}]"
        elif n_books:
            books_str = f"  [{n_books} books]"
        print(f"  {away} @ {home}{ou_str}{pf_str}{books_str}")

        if venue:
            print(f"    Venue: {venue}")
        if flags:
            for fl in flags:
                print(f"    ** {fl}")

        for side in ("away", "home"):
            opp   = "home" if side == "away" else "away"
            team  = g[f"{side}_team"]
            ml    = g.get(f"{side}_ml")
            prob  = g.get(f"{side}_prob", 0.5)
            impl  = g.get(f"{side}_implied", 0.5)
            edge  = g.get(f"{side}_edge", 0.0)
            conv, units = get_conviction(edge, ml)
            sp    = g.get(f"{side}_starter") or "TBD"
            # NOTE: .get(key, default) only applies the default when the key is
            # ABSENT. Pitchers with no stats have the key present but set to None,
            # which then crashes f-string ":.2f" formatting. Coalesce None here.
            def _nz(key, default):
                v = g.get(f"{side}_{key}")
                return default if v is None else v
            era   = _nz("era", LEAGUE_AVG_ERA)
            fip   = _nz("fip", era)
            xfip  = _nz("xfip", fip)
            k9    = _nz("k9", 0.0)
            whip  = _nz("whip", 1.30)
            trend = _nz("trend", "stable")
            last5 = g.get(f"{side}_last5_era")
            ops   = _nz("ops", 0.720)
            wrc   = _nz("wrc_plus", 100)
            starts_detail = g.get(f"{side}_starts_detail", [])

            trend_tag = ""
            if trend == "improving":
                trend_tag = " (^)"
            elif trend == "declining":
                trend_tag = " (v)"

            print(f"    {'Away' if side=='away' else 'Home'}: {team} {ml_str(ml)}")
            print(f"      Model: {prob:.1%}  Implied: {impl:.1%}  Edge: {edge:+.1%}  [{conv}]")
            print(f"      SP: {sp}  ERA {era:.2f}  FIP {fip:.2f}  xFIP {xfip:.2f}  K/9 {k9:.1f}  WHIP {whip:.2f}{trend_tag}")

            # Last 3 starts
            if starts_detail:
                parts = []
                for s in starts_detail[:3]:
                    qs_tag = " QS" if s.get("qs") else ""
                    parts.append(f"{s['date']} vs {s['opp']}: {s['ip']} IP {s['er']} ER {s['k']}K{qs_tag}")
                print(f"      Last starts: {' | '.join(parts)}")
            elif last5 is not None:
                print(f"      Last-5 ERA: {last5:.2f}")

            # Offense line
            opp_ops = g.get(f"{opp}_ops")
            opp_ops = 0.720 if opp_ops is None else opp_ops
            opp_wrc = g.get(f"{opp}_wrc_plus")
            opp_wrc = 100 if opp_wrc is None else opp_wrc
            print(f"      Offense: {team} OPS {ops:.3f} wRC+{wrc}  |  {g[f'{opp}_team']} OPS {opp_ops:.3f} wRC+{opp_wrc}")

            # Pick line
            if units > 0:
                print(f"      >>> PLAY: {team} {ml_str(ml)}  [{conv} {units}u]")
            elif conv == "NO PLAY":
                print(f"      >>> SKIP: insufficient edge ({edge:+.1%})")

        print()

    # Summary
    print("-" * 70)
    print("  PICKS SUMMARY")
    print("-" * 70)
    for g in picks:
        for side in ("away", "home"):
            edge  = g.get(f"{side}_edge", 0.0)
            ml   = g.get(f"{side}_ml")
            conv, units = get_conviction(edge, ml)
            if units > 0:
                team = g[f"{side}_team"]
                opp  = g["home_team"] if side == "away" else g["away_team"]
                prob = g.get(f"{side}_prob", 0.5)
                print(f"  {conv:10s}  {team} vs {opp}  {ml_str(ml)}  {prob:.1%}  {edge:+.1%}  [{units}u]")
    print()


def print_parlay_report(picks: list):
    """Print the parlay builder report."""
    parlays = build_parlays(picks, min_leg_prob=0.57, max_legs=3, top_n=8)

    print()
    print("=" * 70)
    print("  PARLAY BUILDER  (legs: model prob >= 57%, ranked by EV)")
    print("=" * 70)

    if not parlays:
        print("\n  No qualifying legs found (need >= 2 teams with 57%+ model prob).")
        print()
        return

    # Summary table
    print(f"\n  {'#':<3}  {'Legs':<5}  {'Combined%':<11}  {'Parlay ML':<11}  {'EV':>7}")
    print(f"  {'-'*3}  {'-'*5}  {'-'*10}  {'-'*10}  {'-'*7}")
    for i, p in enumerate(parlays, 1):
        print(f"  {i:<3}  {p['n_legs']:<5}  {p['combined_prob']:.1%}{'':4}  {ml_str(p['parlay_ml']):<11}  {p['ev']:+.3f}")

    # Top 3 detailed
    print()
    print("  TOP 3 PARLAYS (detailed)")
    print()
    for i, p in enumerate(parlays[:3], 1):
        print(f"  Parlay #{i}  --  {p['n_legs']}-leg  |  Combined prob: {p['combined_prob']:.1%}  |  "
              f"ML: {ml_str(p['parlay_ml'])}  |  EV: {p['ev']:+.3f}")
        for leg in p["legs"]:
            print(f"    * {leg['team']} {ml_str(leg['ml'])}  ({leg['prob']:.1%}, edge {leg['edge']:+.1%})  "
                  f"SP: {leg['starter']}")
        print()


# -------------------------------------------------
# MAIN PICKS RUNNER
# -------------------------------------------------

def run_daily_picks(target_date: str = None):
    today = target_date or date.today().isoformat()

    # ── FREEZE GATE ──────────────────────────────────────────────────────────
    # Daily picks are locked at the initial run. If today is already frozen,
    # reuse the snapshot and DO NOT pull live odds / recompute. This must run
    # BEFORE any data pull so a re-run can never produce different picks.
    # Override with --refresh to deliberately re-lock.
    try:
        import os as _os
        import mlb_freeze
        _base = _os.path.dirname(_os.path.abspath(__file__))
        _refresh = "--refresh" in sys.argv
        _frozen = None if _refresh else mlb_freeze.load_frozen(today, _base)
        if _frozen:
            print(f"\nMLB Model v3 -- {today}")
            print(f"  [freeze] picks are LOCKED for {today} — reusing snapshot, "
                  f"skipping live odds pull. (--refresh to re-lock)")
            print_picks_report(_frozen, today)
            print_parlay_report(_frozen)
            try:
                mlb_freeze  # summary from frozen picks
                import mlb_summary
                mlb_summary.write_daily_summary(
                    _frozen, today, out_dir=_base,
                    parlays=build_parlays(_frozen, min_leg_prob=0.57, max_legs=3, top_n=8))
            except Exception:
                pass
            return _frozen
    except Exception as _e:
        print(f"  [freeze] gate skipped ({_e}); proceeding to generate.")

    print(f"\nMLB Model v3 -- {today}")
    print("Loading model...")
    try:
        model, active_features = load_model()
        print(f"  Model loaded. Active features: {len(active_features)}")
    except Exception as e:
        print(f"  WARNING: Model unavailable ({e}). Using formula fallback.")
        model = None
        active_features = None

    print("Fetching game data...")
    try:
        game_data = fetch_today_game_data(today)
        print(f"  {len(game_data)} games on slate")
    except Exception as e:
        print(f"  ERROR fetching game data: {e}")
        game_data = []

    print("Fetching odds...")
    odds_map = {}
    try:
        raw_events = fetch_today_odds(target_date=today)
        for raw in raw_events:
            ev = parse_odds_event(raw)
            if ev["away_team"] and ev["home_team"]:
                odds_map[(ev["away_team"], ev["home_team"])] = ev
        print(f"  {len(odds_map)} games with odds")
    except Exception as e:
        print(f"  WARNING: Odds unavailable ({e})")

    picks = []
    game_lookup = {(g["away_team"], g["home_team"]): g for g in game_data}

    # Debug: surface any team name mismatches between the two APIs
    unmatched_odds = [k for k in odds_map if k not in game_lookup]
    unmatched_sched = [k for k in game_lookup if k not in odds_map]
    if unmatched_odds:
        print(f"  [WARN] Odds-only (no MLB schedule match): {unmatched_odds}")
    if unmatched_sched:
        print(f"  [WARN] Schedule-only (no odds match): {unmatched_sched}")

    # Use game_data as the authoritative slate; supplement with odds
    all_matchups = set(game_lookup.keys()) | set(odds_map.keys())

    for (away_team, home_team) in all_matchups:
        auto  = game_lookup.get((away_team, home_team), {})
        ev    = odds_map.get((away_team, home_team), {})

        away_ml      = ev.get("away_ml")
        home_ml      = ev.get("home_ml")
        away_ml_best = ev.get("away_ml_best")
        home_ml_best = ev.get("home_ml_best")
        away_ml_book = ev.get("away_ml_book", "")
        n_books      = ev.get("n_books", 0)
        line_outlier = ev.get("line_outlier", False)
        line_outlier_gap = ev.get("line_outlier_gap", 0.0)

        has_lines = away_ml is not None and home_ml is not None

        venue     = auto.get("venue", "Unknown")
        pf        = PARK_FACTORS.get(venue, auto.get("park_factor", 1.00))
        is_dome   = venue in DOME_PARKS

        away_era  = auto.get("away_era",       LEAGUE_AVG_ERA)
        home_era  = auto.get("home_era",       LEAGUE_AVG_ERA)
        away_fip  = auto.get("away_fip",       away_era)
        home_fip  = auto.get("home_fip",       home_era)
        away_xfip = auto.get("away_xfip",      away_fip)
        home_xfip = auto.get("home_xfip",      home_fip)
        away_k9   = auto.get("away_k9",        0.0)
        home_k9   = auto.get("home_k9",        0.0)
        away_whip = auto.get("away_whip",      1.30)
        home_whip = auto.get("home_whip",      1.30)
        away_gs   = auto.get("away_gs",        0)
        home_gs   = auto.get("home_gs",        0)
        away_last5= auto.get("away_last5_era", None)
        home_last5= auto.get("home_last5_era", None)
        away_trend= auto.get("away_trend",     "stable")
        home_trend= auto.get("home_trend",     "stable")
        away_wp   = auto.get("away_win_pct",   0.500)
        home_wp   = auto.get("home_win_pct",   0.500)
        away_rest = auto.get("away_rest",      5)
        home_rest = auto.get("home_rest",      5)
        away_sp   = auto.get("away_starter",   "TBD")
        home_sp   = auto.get("home_starter",   "TBD")
        away_bp   = auto.get("away_bullpen_era", 4.20)
        home_bp   = auto.get("home_bullpen_era", 4.20)
        h2h_awp   = auto.get("h2h_away_win_pct", 0.5)
        ump_rf    = auto.get("ump_run_factor",   1.0)
        away_l10r = auto.get("away_last10_runs", 4.5)
        home_l10r = auto.get("home_last10_runs", 4.5)
        away_qs   = auto.get("away_qs_rate",   0.50)
        home_qs   = auto.get("home_qs_rate",   0.50)
        away_ops  = auto.get("away_ops",       0.720) or 0.720
        home_ops  = auto.get("home_ops",       0.720) or 0.720
        away_wrc  = auto.get("away_wrc_plus",  100)
        home_wrc  = auto.get("home_wrc_plus",  100)
        away_starts_detail = auto.get("away_starts_detail", [])
        home_starts_detail = auto.get("home_starts_detail", [])

        # Run model
        if model and active_features:
            try:
                base_away_prob = predict_game(model, {
                    "away_era":         away_fip or away_era,
                    "home_era":         home_fip or home_era,
                    "away_fip":         away_fip,
                    "home_fip":         home_fip,
                    "away_xfip":        away_xfip,
                    "home_xfip":        home_xfip,
                    "away_bullpen_era": away_bp,
                    "home_bullpen_era": home_bp,
                    "away_win_pct":     away_wp,
                    "home_win_pct":     home_wp,
                    "away_qs_rate":     away_qs,
                    "home_qs_rate":     home_qs,
                    "away_rest":        away_rest,
                    "home_rest":        home_rest,
                    "park_factor":      pf,
                    "is_dome":          is_dome,
                    "h2h_away_win_pct": h2h_awp,
                    "ump_run_factor":   ump_rf,
                    "away_last10_runs": away_l10r,
                    "home_last10_runs": home_l10r,
                    "away_ops":         away_ops,
                    "home_ops":         home_ops,
                }, active_features=active_features)
            except Exception as e:
                print(f"  Model error for {away_team}@{home_team}: {e}")
                # Formula fallback
                era_diff = (home_fip or home_era) - (away_fip or away_era)
                wp_diff  = away_wp - home_wp
                base_away_prob = max(0.32, min(0.68, 0.47 + era_diff * 0.028 + wp_diff * 0.15))
        else:
            era_diff = (home_fip or home_era) - (away_fip or away_era)
            wp_diff  = away_wp - home_wp
            base_away_prob = max(0.32, min(0.68, 0.47 + era_diff * 0.028 + wp_diff * 0.15))

        game_dict = {
            "away_team":   away_team,
            "home_team":   home_team,
            "away_ml":     away_ml,
            "home_ml":     home_ml,
            "away_rest":   away_rest,
            "home_rest":   home_rest,
            "national_tv": auto.get("national_tv", False),
            "national_tv_network": auto.get("national_tv_network", ""),
            "rain_flag":   auto.get("rain_flag", False),
            "line_outlier": line_outlier,
            "line_outlier_gap": line_outlier_gap,
        }
        away_prob, flags = apply_rule_overlays(game_dict, base_away_prob)
        home_prob = 1.0 - away_prob

        away_implied = ml_to_prob(away_ml) if has_lines else 0.5
        home_implied = ml_to_prob(home_ml) if has_lines else 0.5
        _pd = _EDGE.park_discount(pf) if _EDGE is not None else 1.0
        away_edge = (away_prob - away_implied) * _pd if has_lines else 0.0
        home_edge = (home_prob - home_implied) * _pd if has_lines else 0.0

        game_result = {
            "away_team":    away_team,
            "home_team":    home_team,
            "away_starter": away_sp,
            "home_starter": home_sp,
            "venue":        venue,
            "park_factor":  pf,
            "ou_line":      ev.get("ou_line"),
            "away_ml":      away_ml,
            "home_ml":      home_ml,
            "away_ml_best": away_ml_best,
            "home_ml_best": home_ml_best,
            "away_ml_book": away_ml_book,
            "n_books":      n_books,
            "line_outlier": line_outlier,
            "line_outlier_gap": line_outlier_gap,
            "away_prob":    away_prob,
            "home_prob":    home_prob,
            "away_implied": away_implied,
            "home_implied": home_implied,
            "away_edge":    away_edge,
            "home_edge":    home_edge,
            "away_era":     away_era,
            "home_era":     home_era,
            "away_fip":     away_fip,
            "home_fip":     home_fip,
            "away_xfip":    away_xfip,
            "home_xfip":    home_xfip,
            "away_k9":      away_k9,
            "home_k9":      home_k9,
            "away_whip":    away_whip,
            "home_whip":    home_whip,
            "away_gs":      away_gs,
            "home_gs":      home_gs,
            "away_last5_era": away_last5,
            "home_last5_era": home_last5,
            "away_trend":   away_trend,
            "home_trend":   home_trend,
            "away_wp":      away_wp,
            "home_wp":      home_wp,
            "away_rest":    away_rest,
            "home_rest":    home_rest,
            "away_ops":     away_ops,
            "home_ops":     home_ops,
            "away_wrc_plus": away_wrc,
            "home_wrc_plus": home_wrc,
            "away_starts_detail": away_starts_detail,
            "home_starts_detail": home_starts_detail,
            "away_qs_rate": away_qs,
            "home_qs_rate": home_qs,
            "flags":        flags,
        }
        # Guardrail (2026-07-12): void bets when the model probability implausibly
        # contradicts the no-vig market (corrupted/inverted numberFire feed).
        if _EDGE is not None and hasattr(_EDGE, "gate_game"):
            _EDGE.gate_game(game_result)
        picks.append(game_result)

    # Sort by best edge across both sides
    picks.sort(key=lambda g: max(g.get("away_edge", 0), g.get("home_edge", 0)), reverse=True)

    # Lock the day's picks at this initial run. A re-run reloads the snapshot
    # instead of recomputing against live odds, so daily picks never change.
    try:
        import os as _os
        import mlb_freeze
        _base = _os.path.dirname(_os.path.abspath(__file__))
        _refresh = "--refresh" in sys.argv
        picks = mlb_freeze.load_or_freeze(picks, today, _base,
                                          meta={"source": "mlb_daily"}, refresh=_refresh)
    except Exception as _e:
        print(f"  [freeze] skipped: {_e}")

    print_picks_report(picks, today)
    print_parlay_report(picks)

    # Emit the operator's preferred why/why-not markdown summary (auto, every run).
    try:
        import os
        import mlb_summary
        parlays = build_parlays(picks, min_leg_prob=0.57, max_legs=3, top_n=8)
        path = mlb_summary.write_daily_summary(
            picks, today, out_dir=os.path.dirname(os.path.abspath(__file__)),
            parlays=parlays)
        print(f"\n  Why/why-not summary -> {os.path.basename(path)}")
    except Exception as e:
        print(f"\n  [summary] generation skipped: {e}")

    return picks


# -------------------------------------------------
# CLI
# -------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MLB Daily Picks Runner")
    parser.add_argument("--date", default=None,
                        help="Date to run picks for (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--log-results", action="store_true",
                        help="Enter yesterday's results into the database.")
    args = parser.parse_args()

    if args.log_results:
        print("Result logging not yet implemented. Use run_results.bat.")
        sys.exit(0)

    run_daily_picks(target_date=args.date)
