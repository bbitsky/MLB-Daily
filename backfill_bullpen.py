"""
backfill_bullpen.py — One-time backfill of bullpen ERA using the MLB Stats API.

Why this is needed:
  The original data build called teams/{team_id}/stats which returns only team-level
  aggregates — there are no individual rows to filter by gamesStarted, so every game
  fell back to ERA=4.20 (constant, zero signal).

  This script uses the /stats endpoint with teamId + playerPool=All to get individual
  pitcher stats, filters to relievers (gamesStarted == 0), and computes a proper
  IP-weighted bullpen ERA per team per season.

Run once:
    python backfill_bullpen.py

Takes ~3-5 minutes (30 teams × N seasons, small sleep between calls).
"""

import sqlite3
import time
import requests
from pathlib import Path

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
DB_PATH = Path(__file__).parent / "data" / "mlb.db"
DEFAULT_ERA = 4.20


def mlb_get(endpoint: str, params: dict = None) -> dict:
    url = f"{MLB_API_BASE}/{endpoint}"
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def get_all_team_ids(season: int) -> dict[str, int]:
    """Return {team_name: team_id} for all MLB teams in a season."""
    data = mlb_get("teams", {"sportId": 1, "season": season})
    return {t["name"]: t["id"] for t in data.get("teams", [])}


def get_bullpen_era(team_id: int, season: int) -> float:
    """
    Fetch individual pitcher stats for a team and compute IP-weighted bullpen ERA.
    Relievers = gamesStarted == 0.
    Falls back to DEFAULT_ERA if no usable data.
    """
    try:
        data = mlb_get("stats", {
            "stats":      "season",
            "group":      "pitching",
            "teamId":     team_id,
            "season":     season,
            "sportId":    1,
            "playerPool": "All",
            "gameType":   "R",
        })
    except Exception as e:
        print(f"    API error for team_id={team_id} season={season}: {e}")
        return DEFAULT_ERA

    splits = []
    for stat_group in data.get("stats", []):
        splits.extend(stat_group.get("splits", []))

    if not splits:
        return DEFAULT_ERA

    total_ip = 0.0
    weighted_era = 0.0

    for split in splits:
        stat = split.get("stat", {})
        gs = int(stat.get("gamesStarted", 0) or 0)
        if gs != 0:
            continue  # skip starters

        # Parse IP (stored as "45.1" meaning 45⅓ innings)
        ip_str = str(stat.get("inningsPitched", "0") or "0")
        try:
            parts = ip_str.split(".")
            ip = int(parts[0]) + (int(parts[1]) / 3 if len(parts) > 1 and parts[1] else 0)
        except Exception:
            ip = 0.0

        if ip <= 0:
            continue

        era = float(stat.get("era", DEFAULT_ERA) or DEFAULT_ERA)
        weighted_era += era * ip
        total_ip += ip

    if total_ip <= 0:
        return DEFAULT_ERA

    return round(weighted_era / total_ip, 4)


def backfill():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    seasons = [r[0] for r in cur.execute(
        "SELECT DISTINCT season FROM games ORDER BY season"
    ).fetchall()]

    print(f"Backfilling bullpen ERA for seasons: {seasons}")
    print("Using MLB Stats API — no FanGraphs dependency.\n")

    total_updated = 0

    for season in seasons:
        print(f"Season {season}:")

        try:
            team_ids = get_all_team_ids(season)
        except Exception as e:
            print(f"  Could not fetch team list: {e}")
            continue

        # Get all games for this season
        rows = cur.execute("""
            SELECT g.game_pk, g.away_team, g.home_team
            FROM games g
            WHERE g.season = ? AND g.status = 'Final'
        """, (season,)).fetchall()

        # Build bullpen ERA cache for all teams this season
        era_cache: dict[str, float] = {}
        teams_needed = set()
        for _, away, home in rows:
            teams_needed.add(away)
            teams_needed.add(home)

        for team_name in sorted(teams_needed):
            team_id = team_ids.get(team_name)
            if not team_id:
                print(f"  ⚠️  No team_id for '{team_name}' — skipping")
                era_cache[team_name] = DEFAULT_ERA
                continue
            era = get_bullpen_era(team_id, season)
            era_cache[team_name] = era
            print(f"  {team_name}: bullpen ERA = {era:.2f}")
            time.sleep(0.3)

        # Write to DB
        updated = 0
        for game_pk, away_team, home_team in rows:
            for side, team in [("away", away_team), ("home", home_team)]:
                era = era_cache.get(team, DEFAULT_ERA)
                cur.execute("""
                    INSERT INTO bullpen (game_pk, side, era, whip, k9)
                    VALUES (?, ?, ?, 1.30, 8.5)
                    ON CONFLICT(game_pk, side) DO UPDATE SET era=excluded.era
                """, (game_pk, side, era))
                updated += 1

        con.commit()
        print(f"  → Updated {updated} bullpen rows for {season}\n")
        total_updated += updated

    con.close()
    print(f"Done. Total rows updated: {total_updated}")
    print("Re-run mlb_train.py to retrain with bullpen ERA features.")


if __name__ == "__main__":
    backfill()
