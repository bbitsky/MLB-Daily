# -*- coding: utf-8 -*-
"""
mlb_backfill.py — Backfill new feature columns into the historical games table.

Adds and populates:
  1. away_streak / home_streak  — rolling win/loss streak computed from existing results
  2. is_day_game                — day vs night, from MLB Stats API schedule
  3. away_ops / home_ops        — season OPS, from FanGraphs via pybaseball
  4. away_wrc_plus/home_wrc_plus— season wRC+, same source
  5. away_def_rank/home_def_rank— defensive rank (1=best), FanGraphs team fielding
  6. away_def_rating/home_def_rating — raw Def runs above average

Run once after initial DB build:
    python mlb_backfill.py

Safe to re-run: skips rows already populated, only fills NULLs.
Use --force to overwrite all rows.
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sqlite3
import argparse
import time
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import requests

DB_PATH = Path(__file__).parent / "data" / "mlb.db"
MLB_API = "https://statsapi.mlb.com/api/v1"

# ── FanGraphs abbrev -> MLB full name ──────────────────────────────────────────
_FG_TO_MLB = {
    "ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles",    "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs",         "CWS": "Chicago White Sox",
    "CIN": "Cincinnati Reds",      "CLE": "Cleveland Guardians",
    "COL": "Colorado Rockies",     "DET": "Detroit Tigers",
    "HOU": "Houston Astros",       "KC":  "Kansas City Royals",
    "LAA": "Los Angeles Angels",   "LAD": "Los Angeles Dodgers",
    "MIA": "Miami Marlins",        "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins",      "NYM": "New York Mets",
    "NYY": "New York Yankees",     "OAK": "Oakland Athletics",
    "PHI": "Philadelphia Phillies","PIT": "Pittsburgh Pirates",
    "SD":  "San Diego Padres",     "SF":  "San Francisco Giants",
    "SEA": "Seattle Mariners",     "STL": "St. Louis Cardinals",
    "TB":  "Tampa Bay Rays",       "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays",    "WSH": "Washington Nationals",
}


# ── helpers ────────────────────────────────────────────────────────────────────

def add_columns(con):
    """Add new columns to games table if they don't already exist."""
    new_cols = [
        ("away_streak",      "INTEGER"),
        ("home_streak",      "INTEGER"),
        ("is_day_game",      "INTEGER"),
        ("away_ops",         "REAL"),
        ("home_ops",         "REAL"),
        ("away_wrc_plus",    "INTEGER"),
        ("home_wrc_plus",    "INTEGER"),
        ("away_def_rank",    "INTEGER"),
        ("home_def_rank",    "INTEGER"),
        ("away_def_rating",  "REAL"),
        ("home_def_rating",  "REAL"),
    ]
    cur = con.cursor()
    existing = {r[1] for r in cur.execute("PRAGMA table_info(games)").fetchall()}
    added = []
    for col, typ in new_cols:
        if col not in existing:
            cur.execute(f"ALTER TABLE games ADD COLUMN {col} {typ}")
            added.append(col)
    con.commit()
    if added:
        print(f"  Added columns: {added}")
    else:
        print(f"  All columns already exist.")


# ── 1. Win/loss streaks ────────────────────────────────────────────────────────

def backfill_streaks(con, force=False):
    """
    Compute rolling win/loss streak for each team going into each game.
    Streak = +N (won last N), -N (lost last N), 0 (season start or no history).
    Only uses Final games with known results.
    """
    print("\n[1/4] Computing win/loss streaks...")
    cur = con.cursor()

    if not force:
        remaining = cur.execute(
            "SELECT COUNT(*) FROM games WHERE status='Final' AND away_streak IS NULL"
        ).fetchone()[0]
        if remaining == 0:
            print("  Already populated. Use --force to recompute.")
            return

    # Load all Final games sorted by date
    rows = cur.execute("""
        SELECT game_pk, game_date, away_team, home_team, away_win
        FROM games
        WHERE status = 'Final' AND away_win IS NOT NULL
        ORDER BY game_date ASC, game_pk ASC
    """).fetchall()

    print(f"  Processing {len(rows)} Final games...")

    # Build per-team result history: {team: [1=win, 0=loss, ...]} in chronological order
    team_results: dict = defaultdict(list)
    game_streaks: dict = {}  # game_pk -> (away_streak, home_streak)

    for game_pk, game_date, away_team, home_team, away_win in rows:
        # Compute streaks BEFORE recording this game's result
        def streak_from_history(results):
            if not results:
                return 0
            last = results[-1]
            count = 0
            for r in reversed(results):
                if r == last:
                    count += 1
                else:
                    break
            return count if last == 1 else -count

        away_streak = streak_from_history(team_results[away_team])
        home_streak = streak_from_history(team_results[home_team])
        game_streaks[game_pk] = (away_streak, home_streak)

        # Now record result
        team_results[away_team].append(1 if away_win == 1 else 0)
        team_results[home_team].append(0 if away_win == 1 else 1)

        # Keep only last 20 results per team (enough for any streak)
        if len(team_results[away_team]) > 20:
            team_results[away_team] = team_results[away_team][-20:]
        if len(team_results[home_team]) > 20:
            team_results[home_team] = team_results[home_team][-20:]

    # Write to DB in batches
    batch = [(v[0], v[1], k) for k, v in game_streaks.items()]
    cur.executemany(
        "UPDATE games SET away_streak=?, home_streak=? WHERE game_pk=?", batch
    )
    con.commit()
    print(f"  Streaks written for {len(batch)} games.")


# ── 2. Day / Night ────────────────────────────────────────────────────────────

def backfill_day_night(con, seasons, force=False):
    """Fetch dayNight field from MLB Stats API schedule for each season."""
    print("\n[2/4] Backfilling day/night...")
    cur = con.cursor()

    for season in seasons:
        if not force:
            remaining = cur.execute(
                "SELECT COUNT(*) FROM games WHERE season=? AND status='Final' AND is_day_game IS NULL",
                (season,)
            ).fetchone()[0]
            if remaining == 0:
                print(f"  {season}: already populated.")
                continue

        print(f"  Fetching {season} schedule from MLB API...", end=" ", flush=True)
        try:
            r = requests.get(f"{MLB_API}/schedule", params={
                "sportId": 1,
                "season":  season,
                "gameType": "R",
                "fields": "dates,games,gamePk,dayNight",
            }, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"FAILED ({e})")
            continue

        day_night_map = {}
        for d in data.get("dates", []):
            for g in d.get("games", []):
                gk = g.get("gamePk")
                dn = g.get("dayNight", "night")
                if gk:
                    day_night_map[gk] = 1 if dn == "day" else 0

        batch = [(v, k) for k, v in day_night_map.items()]
        cur.executemany("UPDATE games SET is_day_game=? WHERE game_pk=?", batch)
        con.commit()
        print(f"updated {len(batch)} games.")
        time.sleep(0.5)

    print("  Day/night done.")


# ── MLB team ID lookup ─────────────────────────────────────────────────────────
_MLB_TEAM_IDS = {
    "Arizona Diamondbacks": 109, "Atlanta Braves": 144, "Baltimore Orioles": 110,
    "Boston Red Sox": 111, "Chicago Cubs": 112, "Chicago White Sox": 145,
    "Cincinnati Reds": 113, "Cleveland Guardians": 114, "Colorado Rockies": 115,
    "Detroit Tigers": 116, "Houston Astros": 117, "Kansas City Royals": 118,
    "Los Angeles Angels": 108, "Los Angeles Dodgers": 119, "Miami Marlins": 146,
    "Milwaukee Brewers": 158, "Minnesota Twins": 142, "New York Mets": 121,
    "New York Yankees": 147, "Oakland Athletics": 133, "Philadelphia Phillies": 143,
    "Pittsburgh Pirates": 134, "San Diego Padres": 135, "San Francisco Giants": 137,
    "Seattle Mariners": 136, "St. Louis Cardinals": 138, "Tampa Bay Rays": 139,
    "Texas Rangers": 140, "Toronto Blue Jays": 141, "Washington Nationals": 120,
}
_MLB_ID_TO_NAME = {v: k for k, v in _MLB_TEAM_IDS.items()}


# ── 3. Team OPS (MLB Stats API) ────────────────────────────────────────────────

def backfill_batting_stats(con, seasons, force=False):
    """
    Fill away_ops, home_ops from MLB Stats API team hitting stats.
    Uses /teams/stats endpoint (same source as live data — no pybaseball needed).
    Note: wRC+ not available from MLB API; set to 100 as neutral placeholder.
    """
    print("\n[3/4] Backfilling team batting stats (OPS) via MLB Stats API...")
    cur = con.cursor()

    for season in seasons:
        if not force:
            remaining = cur.execute(
                "SELECT COUNT(*) FROM games WHERE season=? AND away_ops IS NULL",
                (season,)
            ).fetchone()[0]
            if remaining == 0:
                print(f"  {season}: already populated.")
                continue

        print(f"  Fetching MLB API team batting {season}...", end=" ", flush=True)
        try:
            r = requests.get(f"{MLB_API}/teams/stats", params={
                "stats":   "season",
                "group":   "hitting",
                "season":  season,
                "sportId": 1,
            }, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"FAILED ({e})")
            continue

        ops_map = {}
        for stat_group in data.get("stats", []):
            for split in stat_group.get("splits", []):
                team_id = split.get("team", {}).get("id")
                full    = _MLB_ID_TO_NAME.get(team_id)
                if not full:
                    continue
                stat = split.get("stat", {})
                obp  = float(stat.get("obp", 0) or 0)
                slg  = float(stat.get("slg", 0) or 0)
                ops  = obp + slg if (obp + slg) > 0.1 else float(stat.get("ops", 0) or 0)
                ops_map[full] = {"ops": round(ops, 3), "wrc_plus": 100}

        if not ops_map:
            print("FAILED (empty map)")
            continue

        # Apply to all games in this season
        games = cur.execute(
            "SELECT game_pk, away_team, home_team FROM games WHERE season=?", (season,)
        ).fetchall()

        batch = []
        for game_pk, away_team, home_team in games:
            a = ops_map.get(away_team, {})
            h = ops_map.get(home_team, {})
            batch.append((
                a.get("ops", 0.720), h.get("ops", 0.720),
                a.get("wrc_plus", 100), h.get("wrc_plus", 100),
                game_pk,
            ))
        cur.executemany(
            "UPDATE games SET away_ops=?, home_ops=?, away_wrc_plus=?, home_wrc_plus=? "
            "WHERE game_pk=?",
            batch,
        )
        con.commit()
        print(f"updated {len(batch)} games ({len(ops_map)} teams mapped).")

    print("  Batting stats done.")


# ── 4. Defensive rankings (MLB Stats API fielding) ────────────────────────────

def backfill_defensive_ranks(con, seasons, force=False):
    """
    Fill away_def_rank, home_def_rank from MLB Stats API team fielding.
    Ranks teams 1-30 by fielding percentage (best = rank 1).
    Errors per game used as the raw rating (lower = better defense).
    FanGraphs Def is preferable but blocked; this is a solid proxy.
    """
    print("\n[4/4] Backfilling defensive rankings via MLB Stats API...")
    cur = con.cursor()

    for season in seasons:
        if not force:
            remaining = cur.execute(
                "SELECT COUNT(*) FROM games WHERE season=? AND away_def_rank IS NULL",
                (season,)
            ).fetchone()[0]
            if remaining == 0:
                print(f"  {season}: already populated.")
                continue

        print(f"  Fetching MLB API team fielding {season}...", end=" ", flush=True)
        try:
            r = requests.get(f"{MLB_API}/teams/stats", params={
                "stats":   "season",
                "group":   "fielding",
                "season":  season,
                "sportId": 1,
            }, timeout=30)
            r.raise_for_status()
            data = r.json()
            time.sleep(0.5)
        except Exception as e:
            print(f"FAILED ({e})")
            continue

        # Build {team_name: {errors, games, fielding_pct}} map
        field_map = {}
        for stat_group in data.get("stats", []):
            for split in stat_group.get("splits", []):
                team_id = split.get("team", {}).get("id")
                full    = _MLB_ID_TO_NAME.get(team_id)
                if not full:
                    continue
                stat   = split.get("stat", {})
                errors = int(stat.get("errors", 99) or 99)
                games  = int(stat.get("gamesPlayed", 162) or 162)
                fpct   = float(stat.get("fielding", 0) or 0)
                field_map[full] = {
                    "errors":      errors,
                    "errors_pg":   errors / max(games, 1),
                    "fielding_pct": fpct,
                }

        if not field_map:
            print("FAILED (empty map)")
            continue

        # Rank: fewest errors per game = rank 1 (best defense)
        sorted_teams = sorted(field_map.items(), key=lambda x: x[1]["errors_pg"])
        rank_map = {}
        for rank, (team_name, stats) in enumerate(sorted_teams, 1):
            rank_map[team_name] = {
                "rank":   rank,
                # Use negative errors_pg so higher = better (consistent with FanGraphs Def sign)
                "rating": round(-stats["errors_pg"] * 162, 1),
            }

        games = cur.execute(
            "SELECT game_pk, away_team, home_team FROM games WHERE season=?", (season,)
        ).fetchall()

        batch = []
        for game_pk, away_team, home_team in games:
            a = rank_map.get(away_team, {})
            h = rank_map.get(home_team, {})
            batch.append((
                a.get("rank", 15),    h.get("rank", 15),
                a.get("rating", 0.0), h.get("rating", 0.0),
                game_pk,
            ))
        cur.executemany(
            "UPDATE games SET away_def_rank=?, home_def_rank=?, "
            "away_def_rating=?, home_def_rating=? WHERE game_pk=?",
            batch,
        )
        con.commit()
        print(f"updated {len(batch)} games ({len(rank_map)} teams ranked).")

    print("  Defensive rankings done.")


# ── main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill historical feature columns into mlb.db")
    parser.add_argument("--force",   action="store_true", help="Overwrite existing data")
    parser.add_argument("--seasons", nargs="+", type=int,
                        default=[2021, 2022, 2023, 2024, 2025, 2026],
                        help="Seasons to process (default: 2021-2026)")
    parser.add_argument("--skip-streaks",  action="store_true")
    parser.add_argument("--skip-daynight", action="store_true")
    parser.add_argument("--skip-batting",  action="store_true")
    parser.add_argument("--skip-defense",  action="store_true")
    args = parser.parse_args()

    print("MLB Feature Backfill")
    print("=" * 50)
    print(f"DB: {DB_PATH}")
    print(f"Seasons: {args.seasons}")
    if args.force:
        print("Mode: FORCE (overwriting existing data)")
    print()

    con = sqlite3.connect(DB_PATH)

    # Step 0: add columns
    print("[0/4] Adding columns to games table...")
    add_columns(con)

    # Step 1: streaks (no API, just math over existing data)
    if not args.skip_streaks:
        backfill_streaks(con, force=args.force)

    # Step 2: day/night (MLB API, fast)
    if not args.skip_daynight:
        backfill_day_night(con, args.seasons, force=args.force)

    # Step 3: batting stats (pybaseball/FanGraphs)
    if not args.skip_batting:
        backfill_batting_stats(con, args.seasons, force=args.force)

    # Step 4: defensive rankings (pybaseball/FanGraphs)
    if not args.skip_defense:
        backfill_defensive_ranks(con, args.seasons, force=args.force)

    con.close()

    print()
    print("=" * 50)
    print("Backfill complete. Next steps:")
    print("  1. Run: python mlb_train.py   (retrain with new features)")
    print("  2. Run: run_daily.bat          (generate today's picks)")
    print()

    # Quick summary of what's now populated
    con2 = sqlite3.connect(DB_PATH)
    cur2 = con2.cursor()
    total = cur2.execute("SELECT COUNT(*) FROM games WHERE status='Final'").fetchone()[0]
    streaks  = cur2.execute("SELECT COUNT(*) FROM games WHERE away_streak IS NOT NULL").fetchone()[0]
    daynight = cur2.execute("SELECT COUNT(*) FROM games WHERE is_day_game IS NOT NULL").fetchone()[0]
    ops      = cur2.execute("SELECT COUNT(*) FROM games WHERE away_ops IS NOT NULL").fetchone()[0]
    def_r    = cur2.execute("SELECT COUNT(*) FROM games WHERE away_def_rank IS NOT NULL").fetchone()[0]
    con2.close()
    print(f"  Final games total:    {total:,}")
    print(f"  Streaks populated:    {streaks:,}")
    print(f"  Day/night populated:  {daynight:,}")
    print(f"  OPS populated:        {ops:,}")
    print(f"  Def rank populated:   {def_r:,}")
