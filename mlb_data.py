"""
mlb_data.py — Data pipeline for MLB Betting Model v3
Sources:
  - MLB Stats API (free, no key): game results, schedules, starters, venues
  - The Odds API: live daily moneylines / totals
  - pybaseball: pitcher ERA splits, park factors, team batting stats
"""

import os
import sys
import time
import json
import shutil
import atexit
import sqlite3
import platform
import tempfile
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

ODDS_API_KEY  = os.getenv("ODDS_API_KEY", "")
MLB_API_BASE  = "https://statsapi.mlb.com/api/v1"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
DB_PATH       = Path(__file__).parent / "data" / "mlb.db"

# ── FanGraphs 403 workaround ──────────────────────────────────────────────────
# pybaseball (2.2.x) requests FanGraphs with the default "python-requests"
# User-Agent, which FanGraphs blocks -> HTTP 403 on team_batting/pitching_stats/
# team_fielding. Patch pybaseball's request helper to send a browser User-Agent.
# Scoped to pybaseball's html_table_processor so nothing else in the app changes.
# If FanGraphs still blocks (e.g. IP-based), calls fail exactly as before and the
# MLB Stats API fallbacks below kick in — so this can only help, never hurt.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

def _install_fangraphs_ua_patch():
    try:
        from pybaseball.datasources import html_table_processor as _htp
        import requests as _rq

        class _ReqShim:
            """Delegates everything to real requests, but injects a UA on get()."""
            def __getattr__(self, name):
                return getattr(_rq, name)
            def get(self, url, **kwargs):
                headers = dict(kwargs.pop("headers", None) or {})
                headers.setdefault("User-Agent", _BROWSER_UA)
                kwargs.setdefault("timeout", 30)
                return _rq.get(url, headers=headers, **kwargs)

        _htp.requests = _ReqShim()
    except Exception as _e:
        print(f"  [patch] FanGraphs UA patch not applied: {_e}")

_install_fangraphs_ua_patch()

# ── DB corruption / locking safeguards ────────────────────────────────────────
# SQLite corrupts on synced or mounted folders (OneDrive, Dropbox, the Claude
# project mount) because they don't honor the file locking SQLite relies on. So
# the canonical DB stays in the project folder (synced = a portable backup that
# both this machine and the nightly sandbox share), but ALL live SQLite work is
# done on a copy on local, non-synced storage, which is synced back to the
# project folder on exit. WAL mode (persistent in the file header) is enabled on
# the working copy for safer concurrent reads/writes.
#
# Precedence:  MLB_DB_PATH env override  >  local working copy  >  in-place.
_canonical_db_path = DB_PATH
_shadow_db_path = None

def _enable_wal(path):
    try:
        _c = sqlite3.connect(str(path), timeout=30)
        _c.execute("PRAGMA journal_mode=WAL")
        _c.execute("PRAGMA synchronous=NORMAL")
        _c.execute("PRAGMA busy_timeout=30000")
        _c.close()
    except Exception as _e:
        print(f"[DB] Warning: could not enable WAL on {path}: {_e}", file=sys.stderr)

def _register_syncback(shadow, canonical):
    def _sync_shadow_back():
        try:
            if shadow and Path(shadow).exists():
                # Checkpoint the WAL into the main .db file before copying back,
                # so the synced backup is a single self-contained file.
                try:
                    _c = sqlite3.connect(str(shadow), timeout=30)
                    _c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    _c.close()
                except Exception:
                    pass
                Path(canonical).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(shadow), str(canonical))
        except Exception as e:
            print(f"[DB] Warning: could not sync working DB back: {e}", file=sys.stderr)
    atexit.register(_sync_shadow_back)

if os.environ.get("MLB_DB_PATH"):
    # Explicit override — assumed to already be on safe, local storage.
    DB_PATH = Path(os.environ["MLB_DB_PATH"])
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists() and _canonical_db_path.exists():
        shutil.copy2(str(_canonical_db_path), str(DB_PATH))
    _enable_wal(DB_PATH)

elif platform.system() == "Windows":
    # Relocate the live DB off the (synced) project folder to LocalAppData.
    _base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MLB-Daily"
    _base.mkdir(parents=True, exist_ok=True)
    _shadow_db_path = _base / "mlb.db"
    # Refresh the working copy whenever the canonical (synced) backup is newer
    # — e.g. after the nightly sandbox run updates it and it syncs down.
    if _canonical_db_path.exists() and (
        not _shadow_db_path.exists()
        or _canonical_db_path.stat().st_mtime > _shadow_db_path.stat().st_mtime
    ):
        shutil.copy2(str(_canonical_db_path), str(_shadow_db_path))
    _enable_wal(_shadow_db_path)
    _register_syncback(_shadow_db_path, _canonical_db_path)
    DB_PATH = _shadow_db_path

elif platform.system() == "Linux" and " " in str(DB_PATH) and DB_PATH.exists():
    # Sandbox: sqlite3 cannot open FUSE-mounted paths that contain spaces.
    # Copy to a temp dir (no spaces) and use that for all connections.
    _tmp_dir = tempfile.mkdtemp(prefix="mlb_db_")
    _shadow_db_path = Path(_tmp_dir) / "mlb.db"
    shutil.copy2(str(DB_PATH), str(_shadow_db_path))
    _enable_wal(_shadow_db_path)

    def _sync_shadow_back():
        try:
            if _shadow_db_path and _shadow_db_path.exists():
                shutil.copy2(str(_shadow_db_path), str(DB_PATH))
        except Exception as e:
            print(f"[DB] Warning: could not sync shadow DB back: {e}", file=sys.stderr)

    atexit.register(_sync_shadow_back)
    DB_PATH = _shadow_db_path

# Park run-environment factors (relative to league average 1.0)
# >1.0 = hitter-friendly, <1.0 = pitcher-friendly
PARK_FACTORS = {
    "Coors Field":                    1.38,
    "Daikin Park":                    0.97,
    "Great American Ball Park":       1.12,
    "Fenway Park":                    1.09,
    "Guaranteed Rate Field":          1.07,
    "Truist Park":                    1.05,
    "Globe Life Field":               1.04,
    "Wrigley Field":                  1.04,
    "Yankee Stadium":                 1.03,
    "Citizens Bank Park":             1.03,
    "Chase Field":                    1.02,
    "American Family Field":          1.01,
    "loanDepot park":                 1.00,
    "Dodger Stadium":                 0.99,
    "T-Mobile Park":                  0.98,
    "Kauffman Stadium":               0.98,
    "Angel Stadium":                  0.97,
    "Minute Maid Park":               0.97,
    "Target Field":                   0.97,
    "PNC Park":                       0.96,
    "Busch Stadium":                  0.96,
    "Progressive Field":              0.96,
    "Oakland Coliseum":               0.95,
    "Sutter Health Park":             0.95,
    "Oracle Park":                    0.93,
    "Petco Park":                     0.92,
}

DOME_PARKS = {
    "Tropicana Field", "Rogers Centre", "loanDepot park",
    "Minute Maid Park", "Chase Field", "American Family Field",
}

LEAGUE_AVG_ERA = 4.50  # fallback when pitcher stats unavailable

# Venue → timezone label (used for travel penalty calculation)
VENUE_TIMEZONES = {
    # Eastern
    "Fenway Park":               "ET",
    "Yankee Stadium":            "ET",
    "Citi Field":                "ET",
    "Citizens Bank Park":        "ET",
    "Camden Yards":              "ET",
    "Truist Park":               "ET",
    "Great American Ball Park":  "ET",
    "PNC Park":                  "ET",
    "Progressive Field":         "ET",
    "Nationals Park":            "ET",
    "Rogers Centre":             "ET",
    "Tropicana Field":           "ET",
    "loanDepot park":            "ET",
    # Central
    "Wrigley Field":             "CT",
    "Guaranteed Rate Field":     "CT",
    "Target Field":              "CT",
    "Busch Stadium":             "CT",
    "American Family Field":     "CT",
    "Minute Maid Park":          "CT",
    "Globe Life Field":          "CT",
    "Kauffman Stadium":          "CT",
    # Mountain
    "Coors Field":               "MT",
    # Pacific (Chase Field / AZ stays PT-equivalent year-round)
    "Dodger Stadium":            "PT",
    "Oracle Park":               "PT",
    "Petco Park":                "PT",
    "Angel Stadium":             "PT",
    "T-Mobile Park":             "PT",
    "Oakland Coliseum":          "PT",
    "Sutter Health Park":        "PT",
    "Chase Field":               "PT",
}
# Hours west of ET (relative, for shift calculation)
TZ_HOURS = {"ET": 0, "CT": 1, "MT": 2, "PT": 3}

# National TV networks that trigger the "national TV fade" overlay
NATIONAL_TV_NETWORKS = {"ESPN", "ESPN2", "TBS", "FOX", "FS1"}

# All-Star Break end dates by season (games resume the day after)
ALL_STAR_BREAK_END = {
    2023: "2023-07-11",
    2024: "2024-07-16",
    2025: "2025-07-15",
    2026: "2026-07-14",
}

# Module-level cache for team name -> team_id lookups
_TEAM_ID_CACHE = {}  # team_name -> team_id


# ─────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────

def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS games (
        game_pk       INTEGER PRIMARY KEY,
        game_date     TEXT,
        season        INTEGER,
        away_team     TEXT,
        home_team     TEXT,
        away_score    INTEGER,
        home_score    INTEGER,
        away_win      INTEGER,  -- 1 = away won, 0 = home won
        venue         TEXT,
        park_factor   REAL,
        is_dome       INTEGER,
        status        TEXT      -- 'Final', 'Scheduled', etc.
    );

    CREATE TABLE IF NOT EXISTS starters (
        game_pk       INTEGER,
        side          TEXT,     -- 'away' or 'home'
        pitcher_id    INTEGER,
        pitcher_name  TEXT,
        era_season    REAL,
        era_last7     REAL,
        qs_rate       REAL,
        ats_w         INTEGER,
        ats_l         INTEGER,
        rest_days     INTEGER,
        PRIMARY KEY (game_pk, side)
    );

    CREATE TABLE IF NOT EXISTS odds (
        game_pk       INTEGER,
        book          TEXT,
        away_ml       INTEGER,
        home_ml       INTEGER,
        ou_line       REAL,
        fetched_at    TEXT,
        PRIMARY KEY (game_pk, book)
    );

    CREATE TABLE IF NOT EXISTS picks (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        game_pk       INTEGER,
        game_date     TEXT,
        pick_team     TEXT,
        pick_side     TEXT,
        ml            INTEGER,
        my_prob       REAL,
        implied_prob  REAL,
        edge          REAL,
        conviction    TEXT,
        units         REAL,
        result        TEXT,     -- 'W', 'L', 'P' (push), NULL (pending)
        profit_loss   REAL,
        created_at    TEXT
    );

    CREATE TABLE IF NOT EXISTS bullpen (
        game_pk   INTEGER,
        side      TEXT,
        era       REAL,
        whip      REAL,
        k9        REAL,
        PRIMARY KEY (game_pk, side)
    );

    CREATE TABLE IF NOT EXISTS umpires (
        game_pk    INTEGER PRIMARY KEY,
        hp_name    TEXT,
        hp_id      INTEGER,
        run_factor REAL
    );
    """)

    # Add FIP columns to starters table if they don't exist yet
    for col, typ in [("fip", "REAL"), ("xfip", "REAL")]:
        try:
            cur.execute(f"ALTER TABLE starters ADD COLUMN {col} {typ}")
        except Exception:
            pass

    # Add bet flag to picks (1 = user actually bet this pick) if missing
    try:
        cur.execute("ALTER TABLE picks ADD COLUMN bet INTEGER DEFAULT 0")
    except Exception:
        pass

    con.commit()
    con.close()


# ─────────────────────────────────────────────
# MLB STATS API
# ─────────────────────────────────────────────

def _mlb_get(endpoint: str, params: dict = None) -> dict:
    url = f"{MLB_API_BASE}/{endpoint}"
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_season_schedule(season: int) -> list[dict]:
    """Return list of completed regular-season games for a given year."""
    data = _mlb_get("schedule", {
        "sportId": 1,
        "season": season,
        "gameType": "R",
        "fields": "dates,date,games,gamePk,status,detailedState,teams,away,home,score,team,name,venue,id",
    })
    games = []
    for date_block in data.get("dates", []):
        for g in date_block.get("games", []):
            status = g.get("status", {}).get("detailedState", "")
            if status not in ("Final", "Completed Early"):
                continue
            away = g["teams"]["away"]
            home = g["teams"]["home"]
            venue_name = g.get("venue", {}).get("name", "Unknown")
            games.append({
                "game_pk":    g["gamePk"],
                "game_date":  date_block["date"],
                "season":     season,
                "away_team":  away["team"]["name"],
                "home_team":  home["team"]["name"],
                "away_score": away.get("score", 0),
                "home_score": home.get("score", 0),
                "away_win":   1 if away.get("score", 0) > home.get("score", 0) else 0,
                "venue":      venue_name,
                "park_factor": PARK_FACTORS.get(venue_name, 1.00),
                "is_dome":    1 if venue_name in DOME_PARKS else 0,
                "status":     status,
            })
    return games


def fetch_game_starters(game_pk: int) -> dict:
    """Return dict with away/home pitcher id + name from boxscore."""
    try:
        data = _mlb_get(f"game/{game_pk}/boxscore")
        result = {}
        for side in ("away", "home"):
            pitchers = data["teams"][side].get("pitchers", [])
            players  = data["teams"][side].get("players", {})
            if pitchers:
                sp_id   = pitchers[0]
                sp_key  = f"ID{sp_id}"
                sp_data = players.get(sp_key, {})
                sp_name = sp_data.get("person", {}).get("fullName", "Unknown")
                result[side] = {"pitcher_id": sp_id, "pitcher_name": sp_name}
        return result
    except Exception:
        return {}


def fetch_pitcher_season_stats(pitcher_id: int, season: int) -> dict:
    """Return ERA, QS rate, and other stats for a pitcher in a given season."""
    try:
        data = _mlb_get(f"people/{pitcher_id}/stats", {
            "stats": "season",
            "group": "pitching",
            "season": season,
        })
        splits = data.get("stats", [{}])[0].get("splits", [{}])
        if not splits:
            return {}
        s = splits[0].get("stat", {})
        era  = float(s.get("era", 4.50))
        gs   = int(s.get("gamesStarted", 0))
        qs   = int(s.get("qualityStarts", 0))
        qs_rate = (qs / gs) if gs > 0 else 0.0
        return {
            "era":     era,
            "gs":      gs,
            "qs":      qs,
            "qs_rate": qs_rate,
            "ip":      float(s.get("inningsPitched", 0)),
            "k9":      float(s.get("strikeoutsPer9Inn", 0.0)),
            "bb9":     float(s.get("walksPer9Inn", 0.0)),
            "hr9":     float(s.get("homeRunsPer9", 0.0)),
            "whip":    float(s.get("whip", 1.30)),
        }
    except Exception:
        return {}


def fetch_team_record_on_date(team_name: str, season: int, as_of_date: str) -> dict:
    """
    Approximate team record up to (not including) as_of_date by scanning
    completed games from the season schedule cache.
    Returns {w, l, home_w, home_l, away_w, away_l}.
    """
    con = sqlite3.connect(DB_PATH)
    df  = pd.read_sql(
        "SELECT * FROM games WHERE season=? AND game_date < ? AND status='Final'",
        con, params=(season, as_of_date)
    )
    con.close()

    if df.empty:
        return {"w": 0, "l": 0, "home_w": 0, "home_l": 0, "away_w": 0, "away_l": 0}

    as_home = df[df["home_team"] == team_name]
    as_away = df[df["away_team"] == team_name]

    home_w = int((as_home["away_win"] == 0).sum())
    home_l = int((as_home["away_win"] == 1).sum())
    away_w = int((as_away["away_win"] == 1).sum())
    away_l = int((as_away["away_win"] == 0).sum())

    return {
        "w":      home_w + away_w,
        "l":      home_l + away_l,
        "home_w": home_w,
        "home_l": home_l,
        "away_w": away_w,
        "away_l": away_l,
    }


# ─────────────────────────────────────────────
# UMPIRE DATA
# ─────────────────────────────────────────────

def fetch_umpire_for_game(game_pk: int) -> dict:
    """
    Fetch HP umpire info from the boxscore officials list.
    Returns {"hp_name": str, "hp_id": int} or {} on error.
    """
    try:
        data = _mlb_get(f"game/{game_pk}/boxscore")
        officials = data.get("officials", [])
        for official in officials:
            if official.get("officialType") == "Home Plate":
                person = official.get("official", {})
                return {
                    "hp_name": person.get("fullName", "Unknown"),
                    "hp_id":   int(person.get("id", 0)),
                }
        return {}
    except Exception:
        return {}


# ─────────────────────────────────────────────
# BULLPEN DATA
# ─────────────────────────────────────────────

def fetch_team_bullpen_stats(team_name: str, season: int) -> dict:
    """
    Fetch bullpen (relievers-only) ERA, WHIP, K/9 for a team in a given season.
    Returns {"era": float, "whip": float, "k9": float}.
    Falls back to {"era": 4.20, "whip": 1.30, "k9": 8.5} on any error.
    """
    default = {"era": 4.20, "whip": 1.30, "k9": 8.5}
    try:
        # Look up team_id (cached)
        cache_key = f"{team_name}_{season}"
        if cache_key not in _TEAM_ID_CACHE:
            teams_data = _mlb_get("teams", {"sportId": 1, "season": season})
            for t in teams_data.get("teams", []):
                key = f"{t['name']}_{season}"
                _TEAM_ID_CACHE[key] = t["id"]

        team_id = _TEAM_ID_CACHE.get(cache_key)
        if not team_id:
            return default

        # Pull team pitching stats
        stats_data = _mlb_get(f"teams/{team_id}/stats", {
            "stats": "season",
            "group": "pitching",
            "season": season,
            "playerPool": "All",
        })

        splits = []
        for stat_group in stats_data.get("stats", []):
            splits.extend(stat_group.get("splits", []))

        if not splits:
            return default

        # Filter to relievers (gamesStarted == 0)
        total_ip = 0.0
        weighted_era = 0.0
        weighted_whip = 0.0
        weighted_k9 = 0.0

        for split in splits:
            stat = split.get("stat", {})
            gs = int(stat.get("gamesStarted", 0))
            if gs != 0:
                continue
            ip = float(stat.get("inningsPitched", 0) or 0)
            if ip <= 0:
                continue
            era  = float(stat.get("era",  4.20) or 4.20)
            whip = float(stat.get("whip", 1.30) or 1.30)
            k9   = float(stat.get("strikeoutsPer9Inn", 8.5) or 8.5)
            weighted_era  += era  * ip
            weighted_whip += whip * ip
            weighted_k9   += k9   * ip
            total_ip += ip

        if total_ip <= 0:
            return default

        return {
            "era":  weighted_era  / total_ip,
            "whip": weighted_whip / total_ip,
            "k9":   weighted_k9   / total_ip,
        }
    except Exception:
        return default


# ─────────────────────────────────────────────
# ROLLING FEATURES FROM DB
# ─────────────────────────────────────────────

def compute_team_last_n_runs(team_name: str, before_date: str, n: int = 10) -> float:
    """Return average runs scored per game over last n games before before_date."""
    try:
        con = sqlite3.connect(DB_PATH)
        df = pd.read_sql("""
            SELECT CASE WHEN away_team=? THEN away_score ELSE home_score END AS runs
            FROM games
            WHERE (away_team=? OR home_team=?)
              AND game_date < ?
              AND status='Final'
            ORDER BY game_date DESC
            LIMIT ?
        """, con, params=(team_name, team_name, team_name, before_date, n))
        con.close()
        return float(df["runs"].mean()) if len(df) >= 3 else 4.5
    except Exception:
        return 4.5


def compute_h2h_win_pct(away_team: str, home_team: str, season: int, before_date: str) -> float:
    """
    Return away team win% vs this specific home team this season before before_date.
    Returns 0.5 default if fewer than 3 games.
    """
    try:
        con = sqlite3.connect(DB_PATH)
        df = pd.read_sql("""
            SELECT away_win
            FROM games
            WHERE away_team=? AND home_team=?
              AND season=?
              AND game_date < ?
              AND status='Final'
        """, con, params=(away_team, home_team, season, before_date))
        con.close()
        if len(df) < 3:
            return 0.5
        return float(df["away_win"].mean())
    except Exception:
        return 0.5


def compute_day_after_blowout(team_name: str, today_date: str) -> str | None:
    """
    Check if team_name had a blowout win (>=5 run margin) yesterday.
    Returns "won" (blowout win — hangover risk), "lost" (blowout loss),
    or None if no game yesterday or margin < 5.
    """
    try:
        from datetime import date as _date, timedelta
        yesterday = (_date.fromisoformat(today_date) - timedelta(days=1)).isoformat()
        con = sqlite3.connect(DB_PATH)
        df = pd.read_sql("""
            SELECT away_team, home_team, away_score, home_score
            FROM games
            WHERE (away_team=? OR home_team=?)
              AND game_date=? AND status='Final'
            LIMIT 1
        """, con, params=(team_name, team_name, yesterday))
        con.close()
        if df.empty:
            return None
        r = df.iloc[0]
        margin = abs(int(r["away_score"]) - int(r["home_score"]))
        if margin < 5:
            return None
        if r["away_team"] == team_name:
            return "won" if r["away_score"] > r["home_score"] else "lost"
        else:
            return "won" if r["home_score"] > r["away_score"] else "lost"
    except Exception:
        return None


def compute_away_tz_shift(away_team: str, today_venue: str, today_date: str) -> int:
    """
    Compute timezone steps the away team has shifted since their last game.
    Returns 0, 1, 2, or 3 (coast-to-coast). Only counts if last game was <=2 days ago.
    """
    try:
        from datetime import date as _date, timedelta
        last_date = fetch_team_last_game_date(away_team, today_date)
        if not last_date:
            return 0
        # Only apply if they played within 2 days (direct travel)
        gap = (_date.fromisoformat(today_date) - _date.fromisoformat(last_date)).days
        if gap > 2:
            return 0
        con = sqlite3.connect(DB_PATH)
        row = con.execute(
            "SELECT venue FROM games "
            "WHERE (away_team=? OR home_team=?) AND game_date=? AND status='Final' LIMIT 1",
            (away_team, away_team, last_date)
        ).fetchone()
        con.close()
        if not row:
            return 0
        last_tz = TZ_HOURS.get(VENUE_TIMEZONES.get(row[0], "ET"), 0)
        today_tz = TZ_HOURS.get(VENUE_TIMEZONES.get(today_venue, "ET"), 0)
        return abs(today_tz - last_tz)
    except Exception:
        return 0


def compute_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add h2h_away_win_pct, away_last10_runs, home_last10_runs columns
    by computing them row by row from the DB.
    """
    df = df.copy()
    h2h_list = []
    away_runs_list = []
    home_runs_list = []

    for _, row in df.iterrows():
        game_date  = row["game_date"]
        away_team  = row["away_team"]
        home_team  = row["home_team"]
        season     = row["season"]

        h2h_list.append(compute_h2h_win_pct(away_team, home_team, season, game_date))
        away_runs_list.append(compute_team_last_n_runs(away_team, game_date))
        home_runs_list.append(compute_team_last_n_runs(home_team, game_date))

    df["h2h_away_win_pct"] = h2h_list
    df["away_last10_runs"] = away_runs_list
    df["home_last10_runs"] = home_runs_list
    return df


# ─────────────────────────────────────────────
# DERIVED FEATURES (computed from loaded DataFrame — no API calls)
# ─────────────────────────────────────────────

def compute_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute rest_days, away_last10_runs, home_last10_runs, h2h_away_win_pct,
    and ump_run_factor entirely from the loaded DataFrame + umpires DB table.

    Called by load_dataset_from_db() so these features are always populated
    without any additional API calls.
    """
    from collections import deque

    df = df.copy().sort_values("game_date").reset_index(drop=True)

    # ── Rest days ──────────────────────────────────────────────────────────
    # Derive from game_date; reset each season. Default 5 for first game.
    last_game_date: dict[tuple, str] = {}  # (team, season) -> last_date_str
    away_rest_list, home_rest_list = [], []

    for _, row in df.iterrows():
        season = row["season"]
        away, home, date = row["away_team"], row["home_team"], row["game_date"]

        for team, rest_list in [(away, away_rest_list), (home, home_rest_list)]:
            key = (team, season)
            if key in last_game_date:
                d1 = datetime.strptime(last_game_date[key], "%Y-%m-%d")
                d2 = datetime.strptime(date, "%Y-%m-%d")
                rest_list.append(max(1, (d2 - d1).days))
            else:
                rest_list.append(5)  # first game of season

        last_game_date[(away, season)] = date
        last_game_date[(home, season)] = date

    df["away_rest"] = away_rest_list
    df["home_rest"] = home_rest_list

    # ── Last 10 runs scored ────────────────────────────────────────────────
    # Rolling average of runs scored per team (pre-game — state before this game).
    runs_history: dict[tuple, deque] = {}  # (team, season) -> deque(maxlen=10)
    away_last10_list, home_last10_list = [], []

    for _, row in df.iterrows():
        season = row["season"]
        away, home = row["away_team"], row["home_team"]

        for team, lst in [(away, away_last10_list), (home, home_last10_list)]:
            key = (team, season)
            if key not in runs_history:
                runs_history[key] = deque(maxlen=10)
            hist = runs_history[key]
            lst.append(float(sum(hist) / len(hist)) if hist else 4.5)

        # Update AFTER appending (pre-game state)
        key_a, key_h = (away, season), (home, season)
        if key_a not in runs_history: runs_history[key_a] = deque(maxlen=10)
        if key_h not in runs_history: runs_history[key_h] = deque(maxlen=10)
        if pd.notna(row.get("away_score")):
            runs_history[key_a].append(float(row["away_score"]))
        if pd.notna(row.get("home_score")):
            runs_history[key_h].append(float(row["home_score"]))

    df["away_last10_runs"] = away_last10_list
    df["home_last10_runs"] = home_last10_list

    # ── H2H win% (within season, prior games only) ─────────────────────────
    # Tracks wins from the perspective of the away team in prior matchups.
    h2h_records: dict[tuple, list] = {}  # (away, home, season) -> [away_wins, total]
    h2h_list = []

    for _, row in df.iterrows():
        season = row["season"]
        away, home = row["away_team"], row["home_team"]
        # Use canonical key so NYY@BOS and BOS@NYY share history
        canon = (min(away, home), max(away, home), season)
        if canon not in h2h_records:
            h2h_records[canon] = [0, 0]
        wins, total = h2h_records[canon]
        # Express as away-team win rate (flip if away > home alphabetically)
        if away == canon[0]:
            h2h_list.append(wins / total if total > 0 else 0.5)
        else:
            h2h_list.append((total - wins) / total if total > 0 else 0.5)
        # Update
        h2h_records[canon][1] += 1
        if row["away_win"] == 1:
            h2h_records[canon][0] += 1

    df["h2h_away_win_pct"] = h2h_list

    # ── Ump run factor ──────────────────────────────────────────────────────
    # Compute each HP umpire's run tendency from their historical games in DB.
    # run_factor = (ump's avg total runs/game) / (overall league avg runs/game)
    if "ump_run_factor" not in df.columns:
        df["ump_run_factor"] = 1.0
    else:
        try:
            con = sqlite3.connect(DB_PATH)
            ump_games = pd.read_sql("""
                SELECT u.hp_name, g.away_score + g.home_score AS total_runs
                FROM umpires u
                JOIN games g ON u.game_pk = g.game_pk
                WHERE g.status='Final' AND u.hp_name IS NOT NULL
                  AND g.away_score IS NOT NULL AND g.home_score IS NOT NULL
            """, con)
            con.close()

            if len(ump_games) > 100:
                league_avg = ump_games["total_runs"].mean()
                ump_factors = (
                    ump_games.groupby("hp_name")["total_runs"]
                    .mean()
                    .div(league_avg)
                    .to_dict()
                )
                if "hp_name" in df.columns:
                    df["ump_run_factor"] = df["hp_name"].map(ump_factors).fillna(1.0)
        except Exception:
            df["ump_run_factor"] = df["ump_run_factor"].fillna(1.0)

    return df


# ─────────────────────────────────────────────
# THE ODDS API
# ─────────────────────────────────────────────

def fetch_today_odds(regions: str = "us", markets: str = "h2h,totals",
                     target_date: str = None) -> list[dict]:
    """
    Pull today's MLB moneylines and totals from The Odds API.
    Filters to games on target_date only (default: today, US/Eastern).
    The Odds API returns ALL upcoming games if no date filter is applied —
    this caused stale/future-game lines from being included in today's picks.
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    # Build UTC window: Eastern Time is UTC-4 (EDT) or UTC-5 (EST)
    # Use a conservative ±12h window around the target date to cover all TZ offsets
    from_dt = f"{target_date}T00:00:00Z"   # midnight UTC (covers even early ET games)
    # next day midnight UTC = covers all games finishing before then
    next_day = (datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    to_dt = f"{next_day}T09:00:00Z"        # 9 AM UTC next day = 5 AM ET (past any midnight game)

    url = f"{ODDS_API_BASE}/sports/baseball_mlb/odds/"
    params = {
        "apiKey":          ODDS_API_KEY,
        "regions":         regions,
        "markets":         markets,
        "oddsFormat":      "american",
        "commenceTimeFrom": from_dt,
        "commenceTimeTo":   to_dt,
    }
    r = requests.get(url, params=params, timeout=30)
    remaining = r.headers.get("x-requests-remaining", "?")
    print(f"  [Odds API] Requests remaining this month: {remaining}")
    r.raise_for_status()
    events = r.json()

    # Client-side safety filter: only keep events whose commence_time date
    # matches target_date (handles any UTC offset edge cases)
    def _on_target_date(commence_time: str) -> bool:
        try:
            # commence_time format: "2026-06-29T17:05:00Z"
            et_offset = timedelta(hours=4)   # EDT (UTC-4); adjust to -5 in Nov-Mar if needed
            ct = datetime.strptime(commence_time, "%Y-%m-%dT%H:%M:%SZ") - et_offset
            return ct.strftime("%Y-%m-%d") == target_date
        except Exception:
            return True  # if parse fails, keep the event

    filtered = [e for e in events if _on_target_date(e.get("commence_time", ""))]
    if len(filtered) < len(events):
        print(f"  [Odds API] Filtered {len(events) - len(filtered)} future/past games "
              f"(kept {len(filtered)} for {target_date})")

    return filtered


def _ml_to_implied(ml: int) -> float:
    """Convert American moneyline to implied probability."""
    if ml >= 0:
        return 100.0 / (ml + 100.0)
    else:
        return abs(ml) / (abs(ml) + 100.0)


def _implied_to_ml(prob: float) -> int:
    """Convert implied probability to nearest American moneyline integer."""
    prob = max(0.01, min(0.99, prob))
    if prob >= 0.5:
        return -round(prob / (1.0 - prob) * 100)
    else:
        return round((1.0 - prob) / prob * 100)


# Map Odds API team names → MLB Stats API team names.
# The Odds API can lag name changes (e.g. Athletics relocation) or use
# alternate forms. Add any new mismatches here as they appear.
_ODDS_API_TEAM_ALIAS: dict[str, str] = {
    # Athletics moved Oakland→Sacramento for 2025 season;
    # MLB API now returns "Athletics", Odds API may still say "Oakland Athletics"
    "Oakland Athletics":              "Athletics",
    "Sacramento Athletics":           "Athletics",
    # Angels — Odds API sometimes uses the full legal name
    "Los Angeles Angels of Anaheim":  "Los Angeles Angels",
    # Marlins — older alias
    "Florida Marlins":                "Miami Marlins",
    # Expos→Nationals historical edge case
    "Montreal Expos":                 "Washington Nationals",
}


def _normalize_odds_team(name: str) -> str:
    """Normalize an Odds-API team name to what the MLB Stats API returns."""
    return _ODDS_API_TEAM_ALIAS.get(name, name)


# ── Moneyline plausibility bounds ─────────────────────────────────────────────
# Real MLB full-game moneylines essentially never leave a narrow band: the
# heaviest favorites top out around -400 (~0.80 implied) and the longest dogs
# around +320 (~0.24). Anything well past that is bad/mismatched Odds API data
# (e.g. a -5000 line or a +1200 dog) — usually a stale book or a wrong market.
# We drop those quotes rather than let them manufacture a fake "edge".
_ODDS_QUOTE_MAX_IMPLIED     = 0.90   # ~ -900 : discard individual book quotes past this
_ODDS_QUOTE_MIN_IMPLIED     = 0.10   # ~ +900
_ODDS_CONSENSUS_MAX_IMPLIED = 0.88   # ~ -733 : reject the game's line entirely past this
_ODDS_CONSENSUS_MIN_IMPLIED = 0.12   # ~ +733


def _ml_implausible(ml) -> bool:
    """True if a moneyline is missing or too extreme to be a real MLB game line."""
    if ml is None:
        return True
    p = _ml_to_implied(ml)
    return p > _ODDS_CONSENSUS_MAX_IMPLIED or p < _ODDS_CONSENSUS_MIN_IMPLIED


def parse_odds_event(event: dict) -> dict:
    """
    Extract consensus moneyline and O/U from a single Odds API event.

    Uses the MEDIAN implied probability across all bookmakers as the primary
    line (rather than the best/highest line from any single book). This
    prevents a single stale or erroneous book from inflating the apparent
    edge (e.g., one book showing +190 when the true market is -105).

    Returns:
        away_ml / home_ml  — consensus (median) line, used for edge math
        away_ml_best / home_ml_best  — best available line (highest payout)
        away_ml_book / home_ml_book  — book offering the best line
        n_books            — number of bookmakers with h2h markets
        line_outlier       — True if best line is 8+ prob-pct above consensus
        line_outlier_gap   — size of the discrepancy (implied prob points)
    """
    away  = _normalize_odds_team(event["away_team"])
    home  = _normalize_odds_team(event["home_team"])
    start = event["commence_time"]

    away_prices: list[tuple[int, str]] = []   # (ml_price, book_name)
    home_prices: list[tuple[int, str]] = []
    best_ou_line = None
    best_ou_book = None

    for book in event.get("bookmakers", []):
        for mkt in book.get("markets", []):
            if mkt["key"] == "h2h":
                for outcome in mkt["outcomes"]:
                    price = outcome["price"]
                    if outcome["name"] == away:
                        away_prices.append((price, book["title"]))
                    elif outcome["name"] == home:
                        home_prices.append((price, book["title"]))
            elif mkt["key"] == "totals":
                for outcome in mkt["outcomes"]:
                    if outcome["name"] == "Over" and best_ou_line is None:
                        best_ou_line = outcome.get("point")
                        best_ou_book = book["title"]

    def consensus_and_best(prices: list[tuple[int, str]]):
        """Return (consensus_ml, best_ml, best_book, n_books, outlier, gap)."""
        # Layer 1: drop implausible individual quotes (data errors / wrong markets)
        # so a single garbage book can't drag the median to an absurd value.
        prices = [
            (ml, bk) for (ml, bk) in prices
            if _ODDS_QUOTE_MIN_IMPLIED <= _ml_to_implied(ml) <= _ODDS_QUOTE_MAX_IMPLIED
        ]
        if not prices:
            return None, None, None, 0, False, 0.0
        if len(prices) == 1:
            ml, book = prices[0]
            return ml, ml, book, 1, False, 0.0

        # Sort by price (highest = most favorable for bettor)
        prices_sorted = sorted(prices, key=lambda x: x[0], reverse=True)
        best_ml, best_book = prices_sorted[0]

        # Median implied probability across all books
        implied_probs = [_ml_to_implied(p) for p, _ in prices]
        implied_probs.sort()
        mid = len(implied_probs) // 2
        if len(implied_probs) % 2 == 0:
            median_prob = (implied_probs[mid - 1] + implied_probs[mid]) / 2
        else:
            median_prob = implied_probs[mid]

        consensus_ml = _implied_to_ml(median_prob)
        best_implied = _ml_to_implied(best_ml)

        # Outlier: best line is significantly more favorable than consensus
        # (positive gap means the best line shows lower implied prob than consensus)
        gap = median_prob - best_implied  # >0 means best is more favorable
        outlier = gap > 0.08             # >8 probability points = suspicious

        return consensus_ml, best_ml, best_book, len(prices), outlier, round(gap, 4)

    away_cons, away_best, away_book, n_away, away_out, away_gap = consensus_and_best(away_prices)
    home_cons, home_best, home_book, n_home, home_out, home_gap = consensus_and_best(home_prices)

    line_outlier = away_out or home_out
    line_outlier_gap = max(away_gap, home_gap)
    n_books = max(n_away, n_home)

    # Layer 2: reject the whole game's odds if a consensus line is missing or
    # implausibly extreme. It then falls through to "schedule-only" (no play),
    # exactly like a game with no odds — so bad data can't create a fake edge.
    odds_rejected = _ml_implausible(away_cons) or _ml_implausible(home_cons)

    if odds_rejected:
        print(f"  🚫 ODDS REJECTED [{away} @ {home}]: implausible consensus "
              f"({away_cons}/{home_cons}) — treating as no-odds (no pick this game)")
        away_cons = home_cons = None
        away_best = home_best = None
        line_outlier = False
        line_outlier_gap = 0.0
    elif line_outlier:
        print(f"  ⚠️  LINE OUTLIER [{away} @ {home}]: best={away_best:+d}/{home_best:+d} "
              f"vs consensus={away_cons:+d}/{home_cons:+d} (gap={line_outlier_gap:.1%}) "
              f"— using consensus for edge math")

    return {
        "away_team":         away,
        "home_team":         home,
        "start_time":        start,
        "away_ml":           away_cons,           # consensus — used for edge math
        "home_ml":           home_cons,
        "away_ml_best":      away_best,           # best available at any book
        "home_ml_best":      home_best,
        "away_ml_book":      away_book,
        "home_ml_book":      home_book,
        "ou_line":           best_ou_line,
        "n_books":           n_books,
        "line_outlier":      line_outlier,
        "line_outlier_gap":  line_outlier_gap,
        "odds_rejected":     odds_rejected,
        "event_id":          event["id"],
    }


def fetch_historical_odds(date_str: str) -> list[dict]:
    """
    Pull historical odds from The Odds API for a specific date (ISO 8601).
    Requires a paid tier for dates older than a few days.
    date_str format: '2024-06-15T12:00:00Z'
    """
    url = f"{ODDS_API_BASE}/historical/sports/baseball_mlb/odds/"
    params = {
        "apiKey":     ODDS_API_KEY,
        "regions":    "us",
        "markets":    "h2h",
        "oddsFormat": "american",
        "date":       date_str,
    }
    r = requests.get(url, params=params, timeout=15)
    remaining = r.headers.get("x-requests-remaining", "?")
    print(f"  [Odds API Historical] {date_str} | Requests remaining: {remaining}")
    if r.status_code == 422:
        print(f"  [Odds API] Historical data for {date_str} not available on current plan.")
        return []
    r.raise_for_status()
    data = r.json()
    return data.get("data", [])


# ─────────────────────────────────────────────
# PYBASEBALL WRAPPERS
# ─────────────────────────────────────────────

def get_pitcher_stats_pybaseball(season: int) -> pd.DataFrame:
    """
    Fetch full-season pitching stats from Baseball Reference via pybaseball.
    Returns DataFrame indexed by player name with ERA, WHIP, K/9, etc.
    """
    try:
        import pybaseball as pb
        pb.cache.enable()
        df = pb.pitching_stats_bref(season)
        return df
    except Exception as e:
        print(f"  [pybaseball] Could not fetch pitching stats for {season}: {e}")
        return pd.DataFrame()


def get_park_factors_pybaseball(season: int) -> pd.DataFrame:
    """Fetch park factors from Baseball Reference."""
    try:
        import pybaseball as pb
        df = pb.park_factors(season, run_value=True)
        return df
    except Exception as e:
        print(f"  [pybaseball] Could not fetch park factors for {season}: {e}")
        return pd.DataFrame()


def get_team_batting_pybaseball(season: int) -> pd.DataFrame:
    """Fetch team batting stats (wRC+, OPS, etc.)."""
    try:
        import pybaseball as pb
        df = pb.team_batting(season)
        return df
    except Exception as e:
        print(f"  [pybaseball] Could not fetch team batting for {season}: {e}")
        return pd.DataFrame()


# Mapping from MLB Stats API full team names → FanGraphs team abbreviations
_MLB_NAME_TO_FG_ABBREV = {
    "Arizona Diamondbacks":    "ARI",
    "Atlanta Braves":          "ATL",
    "Baltimore Orioles":       "BAL",
    "Boston Red Sox":          "BOS",
    "Chicago Cubs":            "CHC",
    "Chicago White Sox":       "CHW",
    "Cincinnati Reds":         "CIN",
    "Cleveland Guardians":     "CLE",
    "Colorado Rockies":        "COL",
    "Detroit Tigers":          "DET",
    "Houston Astros":          "HOU",
    "Kansas City Royals":      "KCR",
    "Los Angeles Angels":      "LAA",
    "Los Angeles Dodgers":     "LAD",
    "Miami Marlins":           "MIA",
    "Milwaukee Brewers":       "MIL",
    "Minnesota Twins":         "MIN",
    "New York Mets":           "NYM",
    "New York Yankees":        "NYY",
    "Oakland Athletics":       "OAK",
    "Athletics":               "OAK",
    "Philadelphia Phillies":   "PHI",
    "Pittsburgh Pirates":      "PIT",
    "San Diego Padres":        "SDP",
    "San Francisco Giants":    "SFG",
    "Seattle Mariners":        "SEA",
    "St. Louis Cardinals":     "STL",
    "Tampa Bay Rays":          "TBR",
    "Texas Rangers":           "TEX",
    "Toronto Blue Jays":       "TOR",
    "Washington Nationals":    "WSN",
}

_TEAM_BATTING_CACHE: dict = {}  # {season: DataFrame}
_TEAM_BATTING_MLBAPI_CACHE: dict = {}  # {season: {team_name: {ops, wrc_plus}}}


def get_team_batting_mlbapi(season: int) -> dict:
    """
    Fallback team batting (OPS) from the MLB Stats API — same source and method
    as mlb_backfill.py, so live and historical OPS stay consistent. Reliable and
    not subject to FanGraphs' 403 blocking. wRC+ isn't exposed by the MLB API, so
    it stays at the neutral 100 placeholder. Cached once per season.
    Returns {full_team_name: {"ops": float, "wrc_plus": 100}} (empty on failure).
    """
    if season in _TEAM_BATTING_MLBAPI_CACHE:
        return _TEAM_BATTING_MLBAPI_CACHE[season]

    result: dict = {}
    try:
        r = requests.get(f"{MLB_API_BASE}/teams/stats", params={
            "stats":   "season",
            "group":   "hitting",
            "season":  season,
            "sportId": 1,
        }, timeout=30)
        r.raise_for_status()
        data = r.json()
        for stat_group in data.get("stats", []):
            for split in stat_group.get("splits", []):
                name = split.get("team", {}).get("name")
                if not name:
                    continue
                stat = split.get("stat", {})
                obp  = float(stat.get("obp", 0) or 0)
                slg  = float(stat.get("slg", 0) or 0)
                ops  = obp + slg if (obp + slg) > 0.1 else float(stat.get("ops", 0) or 0)
                if ops > 0.1:
                    result[name] = {"ops": round(ops, 3), "wrc_plus": 100}
        if result:
            print(f"  [MLB API] Team batting OPS loaded for {len(result)} teams ({season})")
    except Exception as e:
        print(f"  [MLB API] Could not fetch team batting for {season}: {e}")

    _TEAM_BATTING_MLBAPI_CACHE[season] = result
    return result


def get_team_batting_stats(team_name: str, season: int) -> dict:
    """
    Return OPS and wRC+ for a team from FanGraphs team batting leaderboard.
    If FanGraphs is unavailable (e.g. 403), fall back to MLB Stats API OPS.
    Falls back to league-average defaults only if both sources fail.
    """
    global _TEAM_BATTING_CACHE

    defaults = {"ops": 0.720, "wrc_plus": 100}  # league average

    if season not in _TEAM_BATTING_CACHE:
        df = get_team_batting_pybaseball(season)
        _TEAM_BATTING_CACHE[season] = df

    df = _TEAM_BATTING_CACHE[season]
    if df is None or df.empty:
        # FanGraphs unavailable — use MLB Stats API OPS (real data, wRC+ = 100).
        mlb = get_team_batting_mlbapi(season)
        row = mlb.get(team_name)
        return dict(row) if row else defaults

    abbrev = _MLB_NAME_TO_FG_ABBREV.get(team_name)
    if abbrev is None:
        return defaults

    # FanGraphs team batting uses "Team" column with abbreviations
    team_col = None
    for col in ("Team", "team", "Tm"):
        if col in df.columns:
            team_col = col
            break
    if team_col is None:
        return defaults

    mask = df[team_col].astype(str).str.upper() == abbrev.upper()
    if not mask.any():
        return defaults

    row = df[mask].iloc[0]
    result = {}

    # OPS
    for col in ("OPS", "ops"):
        if col in row and pd.notna(row[col]):
            try:
                result["ops"] = float(row[col])
                break
            except (ValueError, TypeError):
                pass
    result.setdefault("ops", defaults["ops"])

    # wRC+ (FanGraphs uses "wRC+" as column name)
    for col in ("wRC+", "wRC_plus", "wrc+", "wRC"):
        if col in row and pd.notna(row[col]):
            try:
                result["wrc_plus"] = float(row[col])
                break
            except (ValueError, TypeError):
                pass
    result.setdefault("wrc_plus", defaults["wrc_plus"])

    return result



# ─────────────────────────────────────────────
# ADVANCED PITCHER STATS (FanGraphs + recent form)
# ─────────────────────────────────────────────

_FG_CACHE = {}   # {season: DataFrame}  — pulled once per session

def fetch_fg_pitching_stats(season: int) -> "pd.DataFrame":
    """
    Pull FanGraphs season pitching leaderboard via pybaseball (all pitchers, min 0 IP).
    Cached so it only hits the network once per session.
    Returns DataFrame with Name, FIP, xFIP, ERA, K/9, BB/9, WHIP, GS columns.
    Returns empty DataFrame on any failure.
    """
    if season in _FG_CACHE:
        return _FG_CACHE[season]
    try:
        import pybaseball as pb
        pb.cache.enable()
        df = pb.pitching_stats(season, season, qual=0)
        _FG_CACHE[season] = df
        print(f"  [FanGraphs] Loaded {len(df)} pitchers for {season}")
        return df
    except Exception as e:
        print(f"  [FanGraphs] Could not load stats: {e}")
        _FG_CACHE[season] = pd.DataFrame()
        return pd.DataFrame()


def fetch_pitcher_last_n_starts(pitcher_id: int, season: int, n: int = 5) -> dict:
    """
    Pull last N starts for a pitcher from the MLB Stats API game log.
    Returns dict with aggregated stats AND per-start detail lines:
      last_n_era, last_n_ip, last_n_k9, trend,
      starts_detail: list of dicts [{date, opp, ip, er, k, bb, h, result}]
    trend: 'improving', 'declining', 'stable'
    """
    try:
        data = _mlb_get(f"people/{pitcher_id}/stats", {
            "stats":  "gameLog",
            "group":  "pitching",
            "season": season,
        })
        splits = data.get("stats", [{}])[0].get("splits", [])
        # filter to starts only (gamesStarted > 0), chronological order
        starts = [s for s in splits if int(s.get("stat", {}).get("gamesStarted", 0)) > 0]
        starts = starts[-n:]  # last N starts
        if not starts:
            return {}

        total_ip  = sum(float(s["stat"].get("inningsPitched", 0)) for s in starts)
        total_er  = sum(int(s["stat"].get("earnedRuns", 0))       for s in starts)
        total_k   = sum(int(s["stat"].get("strikeOuts", 0))       for s in starts)

        last_n_era = (total_er * 9 / total_ip) if total_ip > 0 else None
        last_n_k9  = (total_k  * 9 / total_ip) if total_ip > 0 else None

        # trend: compare first half vs second half of last N starts
        if len(starts) >= 4:
            mid   = len(starts) // 2
            early = starts[:mid];  late = starts[mid:]
            def era_of(sl):
                ip = sum(float(s["stat"].get("inningsPitched", 0)) for s in sl)
                er = sum(int(s["stat"].get("earnedRuns", 0))       for s in sl)
                return (er * 9 / ip) if ip > 0 else 4.50
            early_era = era_of(early);  late_era = era_of(late)
            if late_era < early_era - 0.75:   trend = "improving"
            elif late_era > early_era + 0.75: trend = "declining"
            else:                              trend = "stable"
        else:
            trend = "stable"

        # Per-start detail lines (most recent last → display newest first)
        starts_detail = []
        for s in reversed(starts):
            st = s.get("stat", {})
            ip_raw = st.get("inningsPitched", "0")
            er     = int(st.get("earnedRuns",  0))
            k      = int(st.get("strikeOuts",  0))
            bb     = int(st.get("baseOnBalls", 0))
            h      = int(st.get("hits",        0))
            date   = s.get("date", "?")
            opp    = s.get("opponent", {}).get("name", "?") if isinstance(s.get("opponent"), dict) else "?"
            # Simple quality start flag: >= 6 IP, <= 3 ER
            try:
                ip_val = float(ip_raw)
                qs_flag = " QS" if ip_val >= 6 and er <= 3 else ""
            except (ValueError, TypeError):
                ip_val = 0.0
                qs_flag = ""
            starts_detail.append({
                "date": date,
                "opp":  opp,
                "ip":   ip_raw,
                "er":   er,
                "k":    k,
                "bb":   bb,
                "h":    h,
                "qs":   qs_flag.strip() == "QS",
            })

        return {
            "last_n_era":     last_n_era,
            "last_n_k9":      last_n_k9,
            "last_n_ip":      total_ip,
            "trend":          trend,
            "starts_detail":  starts_detail,
        }
    except Exception as e:
        return {}


def get_pitcher_advanced(pitcher_id: int, pitcher_name: str,
                         season: int, fg_df: "pd.DataFrame") -> dict:
    """
    Combine FanGraphs (FIP/xFIP) with MLB API recent-form for one pitcher.
    Returns dict: {fip, xfip, last_n_era, trend, ...}
    """
    result = {}

    # ── FanGraphs FIP / xFIP ──────────────────────────────────────────────
    if fg_df is not None and not fg_df.empty:
        # Try exact name match first, then last-name match
        last_name = pitcher_name.split()[-1]
        mask = fg_df["Name"].str.strip() == pitcher_name.strip()
        if not mask.any():
            mask = fg_df["Name"].str.contains(last_name, case=False, na=False)
        if mask.any():
            row = fg_df[mask].iloc[0]
            for col, key in [("FIP","fip"), ("xFIP","xfip"),
                              ("K/9","fg_k9"), ("BB/9","fg_bb9"), ("WHIP","fg_whip")]:
                if col in row and pd.notna(row[col]):
                    result[key] = float(row[col])

    # ── MLB API last 5 starts ────────────────────────────────────────────────
    recent = fetch_pitcher_last_n_starts(pitcher_id, season, n=5)
    result.update(recent)

    return result

# ─────────────────────────────────────────────
# TODAY'S GAME DATA AUTO-FETCH
# ─────────────────────────────────────────────

def fetch_standings(season: int = None) -> dict:
    """
    Pull current standings from MLB Stats API.
    Returns {team_name: {win_pct, wins, losses, streak}} for every team.
    streak is a signed int: +N = W streak of N, -N = L streak of N.
    """
    if season is None:
        season = datetime.now().year
    try:
        data = _mlb_get("standings", {
            "leagueId": "103,104",
            "season": season,
            "standingsType": "regularSeason",
            "hydrate": "team,streak",
        })
        standings = {}
        for record in data.get("records", []):
            for tr in record.get("teamRecords", []):
                name = tr["team"]["name"]
                w    = int(tr.get("wins", 0))
                l    = int(tr.get("losses", 0))
                pct  = w / (w + l) if (w + l) > 0 else 0.500
                # streak: +N win streak, -N loss streak
                streak_info = tr.get("streak", {})
                streak_type = streak_info.get("streakType", "")
                streak_num  = int(streak_info.get("streakNumber", 0))
                if streak_type == "wins":
                    streak = streak_num
                elif streak_type == "losses":
                    streak = -streak_num
                else:
                    streak = 0
                standings[name] = {
                    "win_pct": pct, "wins": w, "losses": l,
                    "streak": streak,
                }
        return standings
    except Exception as e:
        print(f"  [Standings] Error: {e}")
        return {}


def fetch_team_last_game_date(team_name: str, before_date: str) -> str | None:
    """Return the most recent game date for a team before a given date (from DB)."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        row = cur.execute(
            "SELECT MAX(game_date) FROM games "
            "WHERE (away_team=? OR home_team=?) AND game_date < ? AND status='Final'",
            (team_name, team_name, before_date)
        ).fetchone()
        con.close()
        return row[0] if row else None
    except Exception:
        return None


# ── MLB team ID lookup (needed for splits API) ────────────────────────────────
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
    "Athletics": 133,
}

_TEAM_SPLITS_CACHE: dict = {}


def fetch_team_splits(team_name: str, season: int) -> dict:
    """
    Fetch team batting splits vs LHP and RHP from MLB Stats API.
    Returns {"vs_lhp_ops": float, "vs_rhp_ops": float,
             "vs_lhp_avg": float, "vs_rhp_avg": float,
             "vs_lhp_slg": float, "vs_rhp_slg": float}
    """
    cache_key = (team_name, season)
    if cache_key in _TEAM_SPLITS_CACHE:
        return _TEAM_SPLITS_CACHE[cache_key]

    team_id = _MLB_TEAM_IDS.get(team_name)
    result = {}

    if not team_id:
        _TEAM_SPLITS_CACHE[cache_key] = result
        return result

    for hand, key in [("vsLeft", "vs_lhp"), ("vsRight", "vs_rhp")]:
        try:
            data = _mlb_get(f"teams/{team_id}/stats", {
                "stats": hand,
                "group": "hitting",
                "season": season,
            })
            splits = data.get("stats", [])
            for s in splits:
                for sp in s.get("splits", []):
                    stat = sp.get("stat", {})
                    avg = float(stat.get("avg", 0) or 0)
                    slg = float(stat.get("slg", 0) or 0)
                    obp = float(stat.get("obp", 0) or 0)
                    ops = obp + slg if (obp + slg) > 0 else float(stat.get("ops", 0) or 0)
                    result[f"{key}_ops"] = round(ops, 3)
                    result[f"{key}_avg"] = round(avg, 3)
                    result[f"{key}_slg"] = round(slg, 3)
            time.sleep(0.15)
        except Exception as e:
            pass

    _TEAM_SPLITS_CACHE[cache_key] = result
    return result


_DEF_RANK_CACHE: dict = {}


def fetch_team_defensive_ranks(season: int) -> dict:
    """
    Fetch team defensive ratings from pybaseball (FanGraphs team fielding).
    Returns {team_abbrev: {"def_rating": float, "def_rank": int (1=best)}}
    """
    if season in _DEF_RANK_CACHE:
        return _DEF_RANK_CACHE[season]

    try:
        from pybaseball import team_fielding
        df = team_fielding(season)
        # FanGraphs Def column = overall defensive value (runs above average)
        # Normalize team names to full names
        _FG_TO_MLB = {
            "ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves",
            "BAL": "Baltimore Orioles", "BOS": "Boston Red Sox",
            "CHC": "Chicago Cubs", "CWS": "Chicago White Sox",
            "CIN": "Cincinnati Reds", "CLE": "Cleveland Guardians",
            "COL": "Colorado Rockies", "DET": "Detroit Tigers",
            "HOU": "Houston Astros", "KC":  "Kansas City Royals",
            "LAA": "Los Angeles Angels", "LAD": "Los Angeles Dodgers",
            "MIA": "Miami Marlins", "MIL": "Milwaukee Brewers",
            "MIN": "Minnesota Twins", "NYM": "New York Mets",
            "NYY": "New York Yankees", "OAK": "Oakland Athletics",
            "PHI": "Philadelphia Phillies", "PIT": "Pittsburgh Pirates",
            "SD":  "San Diego Padres", "SF":  "San Francisco Giants",
            "SEA": "Seattle Mariners", "STL": "St. Louis Cardinals",
            "TB":  "Tampa Bay Rays", "TEX": "Texas Rangers",
            "TOR": "Toronto Blue Jays", "WSH": "Washington Nationals",
        }
        # Find Def column (may be labeled "Def" or "Def_")
        def_col = next((c for c in df.columns if c.lower().startswith("def")), None)
        if def_col is None:
            _DEF_RANK_CACHE[season] = {}
            return {}

        # Aggregate by team (some seasons have separate entries per team)
        if "Team" in df.columns:
            team_col = "Team"
        elif "team_name" in df.columns:
            team_col = "team_name"
        else:
            _DEF_RANK_CACHE[season] = {}
            return {}

        agg = df.groupby(team_col)[def_col].sum().reset_index()
        agg.columns = ["abbrev", "def_val"]
        agg = agg.sort_values("def_val", ascending=False).reset_index(drop=True)
        agg["def_rank"] = agg.index + 1  # 1 = best defense

        result = {}
        for _, row in agg.iterrows():
            full_name = _FG_TO_MLB.get(row["abbrev"], "")
            if full_name:
                result[full_name] = {
                    "def_rating": float(row["def_val"]),
                    "def_rank":   int(row["def_rank"]),
                }
        _DEF_RANK_CACHE[season] = result
        return result
    except Exception as e:
        print(f"  [DefRank] Error: {e}")
        _DEF_RANK_CACHE[season] = {}
        return {}


def fetch_today_game_data(target_date: str = None) -> list[dict]:
    """
    Auto-fetch everything needed to run today's model:
      - Today's scheduled games + venues
      - Probable starters + their current-season stats
      - Current team standings (win%)
      - Rest days (from DB history)
      - Bullpen ERA for both sides
      - Last 10 games runs scored for both teams
      - H2H win% for away team vs home team this season
      - HP umpire name + run factor
      - Series game number + games in series
      - National TV detection (ESPN/FOX/TBS/FS1)
      - Day-after-blowout flag (auto from DB)
      - Away team timezone shift (auto from DB + venue map)

    Returns a list of game dicts compatible with the model's overlay format.
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")
    season = int(target_date[:4])

    print(f"  [Auto-fetch] Pulling today's schedule for {target_date}...")

    # 1. Today's schedule with probable pitchers + venue + broadcasts
    try:
        data = _mlb_get("schedule", {
            "sportId":  1,
            "date":     target_date,
            "gameType": "R",
            "hydrate":  "probablePitcher,venue,linescore,broadcasts",
        })
    except Exception as e:
        print(f"  [Auto-fetch] Schedule fetch failed: {e}")
        return []

    # 2. Standings for win%
    print(f"  [Auto-fetch] Fetching {season} standings...")
    standings = fetch_standings(season)

    games_out = []
    dates = data.get("dates", [])
    if not dates:
        print("  [Auto-fetch] No games found for today.")
        return []

    all_games = [g for d in dates for g in d.get("games", [])]
    print(f"  [Auto-fetch] {len(all_games)} games on slate. Fetching pitcher stats...")

    # Pull FanGraphs leaderboard once for all pitchers
    print(f"  [Auto-fetch] Loading FanGraphs data for {season}...")
    fg_df = fetch_fg_pitching_stats(season)

    # Pull team batting stats once for the full session (OPS, wRC+)
    print(f"  [Auto-fetch] Loading FanGraphs team batting for {season}...")
    get_team_batting_pybaseball(season)  # populates _TEAM_BATTING_CACHE

    # Pull defensive rankings once for all teams
    print(f"  [Auto-fetch] Loading defensive rankings for {season}...")
    def_ranks = fetch_team_defensive_ranks(season)

    # Look up existing umpire run factors from DB
    ump_run_factors = {}
    try:
        con = sqlite3.connect(DB_PATH)
        ump_df = pd.read_sql("SELECT hp_name, run_factor FROM umpires", con)
        con.close()
        for _, urow in ump_df.iterrows():
            if urow["hp_name"] and urow["run_factor"] is not None:
                ump_run_factors[urow["hp_name"]] = float(urow["run_factor"])
    except Exception:
        pass

    for g in all_games:
        status = g.get("status", {}).get("detailedState", "")
        if status in ("Postponed", "Cancelled"):
            continue

        game_pk    = g["gamePk"]
        away_info  = g["teams"]["away"]
        home_info  = g["teams"]["home"]
        venue_name = g.get("venue", {}).get("name", "Unknown")

        away_name = away_info["team"]["name"]
        home_name = home_info["team"]["name"]

        # ── Series context ──
        series_game_num  = g.get("seriesGameNumber", 1)
        games_in_series  = g.get("gamesInSeries", 3)

        # ── Day / Night ──
        is_day_game = g.get("dayNight", "night").lower() == "day"

        # ── Win streaks from standings ──
        away_streak = standings.get(away_name, {}).get("streak", 0)
        home_streak = standings.get(home_name, {}).get("streak", 0)

        # ── National TV auto-detect ──
        broadcasts = g.get("broadcasts", [])
        national_tv_network = next(
            (b.get("name") for b in broadcasts
             if b.get("name") in NATIONAL_TV_NETWORKS
             and b.get("type", "").upper() == "TV"),
            None,
        )
        national_tv = national_tv_network is not None

        # ── Day-after-blowout (auto from DB) ──
        away_blowout = compute_day_after_blowout(away_name, target_date)
        home_blowout = compute_day_after_blowout(home_name, target_date)
        if home_blowout == "won":
            day_after_blowout_team = "home"
        elif away_blowout == "won":
            day_after_blowout_team = "away"
        else:
            day_after_blowout_team = None

        # ── Away team timezone shift ──
        away_tz_shift = compute_away_tz_shift(away_name, venue_name, target_date)

        # Probable pitchers (may be absent)
        away_prob = away_info.get("probablePitcher", {})
        home_prob = home_info.get("probablePitcher", {})

        def get_pitcher_stats(probable: dict) -> dict:
            if not probable:
                return {}
            pid  = probable.get("id")
            name = probable.get("fullName", "TBD")
            if not pid:
                return {"name": name}
            # Season stats from MLB API
            stats = fetch_pitcher_season_stats(pid, season)
            stats["name"] = name
            stats["id"]   = pid
            # Pitcher handedness from player profile
            try:
                pdata = _mlb_get(f"people/{pid}", {"hydrate": "currentTeam"})
                person = pdata.get("people", [{}])[0]
                stats["pitch_hand"] = person.get("pitchHand", {}).get("code", "R")
                stats["bat_side"]   = person.get("batSide",   {}).get("code", "R")
            except Exception:
                stats["pitch_hand"] = "R"
            # Advanced stats: FIP, xFIP, recent form
            adv = get_pitcher_advanced(pid, name, season, fg_df)
            stats.update(adv)
            return stats

        away_sp = get_pitcher_stats(away_prob)
        home_sp = get_pitcher_stats(home_prob)

        # Rest days from DB
        def rest_days(team, date):
            last = fetch_team_last_game_date(team, date)
            if not last:
                return 5  # default
            from datetime import date as dclass
            d1 = dclass.fromisoformat(last)
            d2 = dclass.fromisoformat(date)
            return max(1, (d2 - d1).days)

        away_rest = rest_days(away_name, target_date)
        home_rest = rest_days(home_name, target_date)

        # Win% from standings (fall back to 0.500)
        away_wp = standings.get(away_name, {}).get("win_pct", 0.500)
        home_wp = standings.get(home_name, {}).get("win_pct", 0.500)

        pf      = PARK_FACTORS.get(venue_name, 1.00)
        is_dome = venue_name in DOME_PARKS

        # Bullpen stats
        time.sleep(0.2)
        away_bullpen = fetch_team_bullpen_stats(away_name, season)
        time.sleep(0.2)
        home_bullpen = fetch_team_bullpen_stats(home_name, season)

        # Last 10 games runs scored
        away_last10 = compute_team_last_n_runs(away_name, target_date)
        home_last10 = compute_team_last_n_runs(home_name, target_date)

        # H2H win%
        h2h_wp = compute_h2h_win_pct(away_name, home_name, season, target_date)

        # Umpire
        hp_umpire = ""
        ump_run_factor = 1.0
        try:
            ump_info = fetch_umpire_for_game(game_pk)
            hp_umpire = ump_info.get("hp_name", "")
            if hp_umpire and hp_umpire in ump_run_factors:
                ump_run_factor = ump_run_factors[hp_umpire]
        except Exception:
            pass

        # Team offensive stats (OPS, wRC+) from FanGraphs
        away_bat = get_team_batting_stats(away_name, season)
        home_bat = get_team_batting_stats(home_name, season)

        # vs LHP/RHP batting splits (cached per team per season)
        away_splits = fetch_team_splits(away_name, season)
        home_splits = fetch_team_splits(home_name, season)

        # Pitcher handedness for split lookup
        away_sp_hand = away_sp.get("pitch_hand", "R")
        home_sp_hand = home_sp.get("pitch_hand", "R")

        # OPS vs the opposing starter's handedness
        away_vs_sp_ops = away_splits.get(
            f"vs_{'lhp' if home_sp_hand == 'L' else 'rhp'}_ops", 0.720) or 0.720
        home_vs_sp_ops = home_splits.get(
            f"vs_{'lhp' if away_sp_hand == 'L' else 'rhp'}_ops", 0.720) or 0.720

        # Defensive rankings
        away_def = def_ranks.get(away_name, {})
        home_def = def_ranks.get(home_name, {})
        n_teams = 30
        away_def_rank = away_def.get("def_rank", 15)
        home_def_rank = home_def.get("def_rank", 15)
        away_def_rating = away_def.get("def_rating", 0.0)
        home_def_rating = home_def.get("def_rating", 0.0)

        game_dict = {
            "game_pk":       game_pk,
            "away_team":     away_name,
            "home_team":     home_name,
            "venue":         venue_name,
            "park_factor":   pf,
            "is_dome":       is_dome,
            "away_starter":  away_sp.get("name", "TBD"),
            "home_starter":  home_sp.get("name", "TBD"),
            "away_era":      away_sp.get("era",     LEAGUE_AVG_ERA),
            "home_era":      home_sp.get("era",     LEAGUE_AVG_ERA),
            "away_qs_rate":  away_sp.get("qs_rate", 0.50),
            "home_qs_rate":  home_sp.get("qs_rate", 0.50),
            "away_k9":       away_sp.get("k9",      0.0),
            "home_k9":       home_sp.get("k9",      0.0),
            "away_whip":     away_sp.get("whip",    1.30),
            "home_whip":     home_sp.get("whip",    1.30),
            "away_gs":       away_sp.get("gs",         0),
            "home_gs":       home_sp.get("gs",         0),
            "away_rest":     away_rest,
            "home_rest":     home_rest,
            "away_win_pct":  away_wp,
            "home_win_pct":  home_wp,
            # FanGraphs advanced
            "away_fip":      away_sp.get("fip",        LEAGUE_AVG_ERA),
            "home_fip":      home_sp.get("fip",        LEAGUE_AVG_ERA),
            "away_xfip":     away_sp.get("xfip",       LEAGUE_AVG_ERA),
            "home_xfip":     home_sp.get("xfip",       LEAGUE_AVG_ERA),
            # Recent form (last 5 starts)
            "away_last5_era":     away_sp.get("last_n_era",    None),
            "home_last5_era":     home_sp.get("last_n_era",    None),
            "away_trend":         away_sp.get("trend",         "stable"),
            "home_trend":         home_sp.get("trend",         "stable"),
            "away_starts_detail": away_sp.get("starts_detail", []),
            "home_starts_detail": home_sp.get("starts_detail", []),
            # New features
            "away_bullpen_era":  away_bullpen.get("era",  4.20),
            "home_bullpen_era":  home_bullpen.get("era",  4.20),
            "away_last10_runs":  away_last10,
            "home_last10_runs":  home_last10,
            "h2h_away_win_pct":  h2h_wp,
            "hp_umpire":         hp_umpire,
            "ump_run_factor":    ump_run_factor,
            # Team offensive stats (FanGraphs)
            "away_ops":      away_bat.get("ops",      0.720),
            "home_ops":      home_bat.get("ops",      0.720),
            "away_wrc_plus": away_bat.get("wrc_plus", 100),
            "home_wrc_plus": home_bat.get("wrc_plus", 100),
            # vs LHP/RHP splits
            "away_vs_lhp_ops": away_splits.get("vs_lhp_ops", 0.720),
            "away_vs_rhp_ops": away_splits.get("vs_rhp_ops", 0.720),
            "home_vs_lhp_ops": home_splits.get("vs_lhp_ops", 0.720),
            "home_vs_rhp_ops": home_splits.get("vs_rhp_ops", 0.720),
            "away_vs_lhp_avg": away_splits.get("vs_lhp_avg", 0.250),
            "away_vs_rhp_avg": away_splits.get("vs_rhp_avg", 0.250),
            "home_vs_lhp_avg": home_splits.get("vs_lhp_avg", 0.250),
            "home_vs_rhp_avg": home_splits.get("vs_rhp_avg", 0.250),
            # OPS vs today's opposing starter handedness
            "away_vs_sp_ops": away_vs_sp_ops,
            "home_vs_sp_ops": home_vs_sp_ops,
            "away_sp_hand":   away_sp_hand,
            "home_sp_hand":   home_sp_hand,
            # Win streaks (+N = winning streak, -N = losing streak)
            "away_streak": away_streak,
            "home_streak": home_streak,
            # Defensive rankings (1 = best defense in MLB)
            "away_def_rank":   away_def_rank,
            "home_def_rank":   home_def_rank,
            "away_def_rating": away_def_rating,
            "home_def_rating": home_def_rating,
            # Day/night
            "is_day_game": is_day_game,
            # Auto-computed contextual triggers
            "game_date":              target_date,
            "series_game_num":        series_game_num,
            "games_in_series":        games_in_series,
            "national_tv":            national_tv,
            "national_tv_network":    national_tv_network or "",
            "day_after_blowout_team": day_after_blowout_team,
            "away_tz_shift":          away_tz_shift,
        }
        games_out.append(game_dict)
        time.sleep(0.2)  # be polite to the free API

    print(f"  [Auto-fetch] Done -- {len(games_out)} games with data.")
    return games_out


# ---------------------------------------------
# HISTORICAL DATA BUILDER
# ---------------------------------------------

def build_historical_dataset(seasons: list, max_games_per_season: int = None,
                              delay: float = 0.3):
    """
    Pull historical games + starters + stats and store in SQLite.
    seasons: e.g. [2022, 2023, 2024, 2025]
    delay:   seconds between MLB API calls to avoid rate-limiting
    """
    init_db()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    for season in seasons:
        print(f"\n-- Fetching {season} season schedule...")
        games = fetch_season_schedule(season)
        if max_games_per_season:
            games = games[:max_games_per_season]

        print(f"   Found {len(games)} completed games.")
        print(f"   Pulling pybaseball pitching stats for {season}...")
        pb_stats = get_pitcher_stats_pybaseball(season)

        for i, g in enumerate(games):
            pk = g["game_pk"]
            existing = cur.execute("SELECT 1 FROM games WHERE game_pk=?", (pk,)).fetchone()
            if existing:
                continue

            cur.execute("""
                INSERT OR IGNORE INTO games
                (game_pk, game_date, season, away_team, home_team,
                 away_score, home_score, away_win, venue, park_factor, is_dome, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (pk, g["game_date"], g["season"], g["away_team"], g["home_team"],
                  g["away_score"], g["home_score"], g["away_win"],
                  g["venue"], g["park_factor"], g["is_dome"], g["status"]))

            time.sleep(delay)
            starters = fetch_game_starters(pk)

            for side, sp in starters.items():
                pid   = sp["pitcher_id"]
                pname = sp["pitcher_name"]
                sp_stats = {}
                if not pb_stats.empty:
                    mask = pb_stats["Name"].str.contains(pname.split()[-1], case=False, na=False)
                    if mask.any():
                        row = pb_stats[mask].iloc[0]
                        era = float(row.get("ERA", 4.50))
                        gs  = int(row.get("GS",  0))
                        qs  = int(row.get("QS",  0))
                        sp_stats = {
                            "era":     era, "gs": gs, "qs": qs,
                            "qs_rate": qs / gs if gs > 0 else 0.0,
                            "ip":      float(row.get("IP", 0)),
                            "k9":      float(row.get("K/9", 0)),
                            "bb9":     float(row.get("BB/9", 0)),
                            "whip":    float(row.get("WHIP", 1.30)),
                            "fip":     float(row.get("FIP", float("nan"))) if "FIP" in row.index else float("nan"),
                            "xfip":    float(row.get("xFIP", float("nan"))) if "xFIP" in row.index else float("nan"),
                        }
                if not sp_stats:
                    time.sleep(delay)
                    sp_stats = fetch_pitcher_season_stats(pid, g["season"])
                era_val  = sp_stats.get("era",     4.50)
                qs_rate  = sp_stats.get("qs_rate", 0.0)
                fip_val  = sp_stats.get("fip",     None)
                xfip_val = sp_stats.get("xfip",    None)
                cur.execute("""
                    INSERT OR IGNORE INTO starters
                    (game_pk, side, pitcher_id, pitcher_name,
                     era_season, qs_rate, rest_days, fip, xfip)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (pk, side, pid, pname, era_val, qs_rate, 5, fip_val, xfip_val))

            try:
                ump = fetch_umpire_for_game(pk)
                if ump:
                    cur.execute("""
                        INSERT OR IGNORE INTO umpires (game_pk, hp_name, hp_id, run_factor)
                        VALUES (?,?,?,?)
                    """, (pk, ump.get("hp_name"), ump.get("hp_id"), None))
            except Exception:
                pass

            try:
                for side, tname in [("away", g["away_team"]), ("home", g["home_team"])]:
                    bp = fetch_team_bullpen_stats(tname, g["season"])
                    cur.execute("""
                        INSERT OR IGNORE INTO bullpen (game_pk, side, era, whip, k9)
                        VALUES (?,?,?,?,?)
                    """, (pk, side, bp["era"], bp["whip"], bp["k9"]))
                    time.sleep(0.1)
            except Exception:
                pass

            if (i + 1) % 50 == 0:
                con.commit()
                print(f"   ...{i+1}/{len(games)} games processed")

        con.commit()
        print(f"   Season {season} complete.")

    con.close()
    return load_dataset_from_db()


# ---------------------------------------------
# DATASET LOADER
# ---------------------------------------------

def load_dataset_from_db():
    """Load the full historical dataset from SQLite into a DataFrame."""
    init_db()
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql("""
        SELECT
            g.game_pk, g.game_date, g.season, g.away_team, g.home_team,
            g.away_score, g.home_score, g.away_win,
            g.venue, g.park_factor, g.is_dome, g.status,
            a.era_season AS away_era,  h.era_season AS home_era,
            a.fip        AS away_fip,  h.fip        AS home_fip,
            a.qs_rate    AS away_qs,   h.qs_rate    AS home_qs,
            a.rest_days  AS away_rest, h.rest_days  AS home_rest,
            a.pitcher_name AS away_starter, h.pitcher_name AS home_starter,
            ab.era AS away_bullpen_era, hb.era AS home_bullpen_era,
            u.hp_name      AS hp_name,
            u.run_factor   AS ump_run_factor
        FROM games g
        LEFT JOIN starters a  ON g.game_pk=a.game_pk AND a.side='away'
        LEFT JOIN starters h  ON g.game_pk=h.game_pk AND h.side='home'
        LEFT JOIN bullpen  ab ON g.game_pk=ab.game_pk AND ab.side='away'
        LEFT JOIN bullpen  hb ON g.game_pk=hb.game_pk AND hb.side='home'
        LEFT JOIN umpires  u  ON g.game_pk=u.game_pk
        WHERE g.status='Final'
        ORDER BY g.game_date
    """, con)
    con.close()
    if "away_qs" in df.columns:
        df = df.rename(columns={"away_qs": "away_qs_rate", "home_qs": "home_qs_rate"})
    df = compute_derived_features(df)
    return df


def get_db_summary():
    """Return summary stats about what's in the DB."""
    init_db()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    total = cur.execute("SELECT COUNT(*) FROM games WHERE status='Final'").fetchone()[0]
    by_year = {}
    for row in cur.execute(
        "SELECT season, COUNT(*) FROM games WHERE status='Final' GROUP BY season ORDER BY season"
    ):
        by_year[row[0]] = row[1]
    picks_total = cur.execute("SELECT COUNT(*) FROM picks").fetchone()[0]
    con.close()
    return {"total_games": total, "games_by_year": by_year, "total_picks": picks_total}


def load_odds_from_db(game_pk: int = None):
    """Load stored odds from DB."""
    con = sqlite3.connect(DB_PATH)
    if game_pk:
        df = pd.read_sql("SELECT * FROM odds WHERE game_pk=?", con, params=(game_pk,))
    else:
        df = pd.read_sql("SELECT * FROM odds", con)
    con.close()
    return df


# ---------------------------------------------
# CLI
# ---------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MLB Data Pipeline")
    parser.add_argument("--test",  action="store_true", help="Test API connectivity")
    parser.add_argument("--build", action="store_true", help="Pull historical data and store in DB")
    parser.add_argument("--seasons", nargs="+", type=int,
                        default=[2021, 2022, 2023, 2024, 2025],
                        help="Seasons to pull (default: 2021-2025)")
    args = parser.parse_args()

    if args.build:
        print(f"Building historical dataset for seasons: {args.seasons}")
        build_historical_dataset(args.seasons)
        summary = get_db_summary()
        print(f"\nDatabase now contains {summary['total_games']} games:")
        for yr, cnt in summary["games_by_year"].items():
            print(f"  {yr}: {cnt} games")
    else:
        print("MLB Data Pipeline -- Connection Test")
        # odds sanity guard active
