#!/usr/bin/env python3
"""
repair_mlb_db.py  --  Repair a corrupt/locked data/mlb.db.

WHY: On 2026-07-01 the database was found in a "database disk image is malformed"
state. Root cause: the file was locked open mid-write by a running process (a live
-journal was present and could not be cleared). The picks table (your betting
history) was preserved and exported to picks_history_backup.csv.

BEFORE RUNNING:
  1. Close the MLB app / any script or DB browser that has data/mlb.db open.
  2. Then run:  python repair_mlb_db.py

WHAT IT DOES:
  - If mlb.db opens cleanly, it does nothing (no repair needed).
  - If mlb.db is malformed, it backs it up to data/mlb.db.corrupt-<timestamp>,
    rebuilds a fresh schema (games, starters, odds, picks, bullpen, umpires),
    and re-imports your pick history from picks_history_backup.csv.
  - The daily tables (games/starters/odds/bullpen/umpires) are left empty on
    purpose; your normal daily data pull repopulates them on the next run.
"""
import os, csv, sqlite3, shutil, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DB   = ROOT / "data" / "mlb.db"
CSV  = ROOT / "picks_history_backup.csv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    game_pk INTEGER PRIMARY KEY, game_date TEXT, season INTEGER,
    away_team TEXT, home_team TEXT, away_score INTEGER, home_score INTEGER,
    away_win INTEGER, venue TEXT, park_factor REAL, is_dome INTEGER, status TEXT);
CREATE TABLE IF NOT EXISTS starters (
    game_pk INTEGER, side TEXT, pitcher_id INTEGER, pitcher_name TEXT,
    era_season REAL, era_last7 REAL, qs_rate REAL, ats_w INTEGER, ats_l INTEGER,
    rest_days INTEGER, fip REAL, xfip REAL, PRIMARY KEY (game_pk, side));
CREATE TABLE IF NOT EXISTS odds (
    game_pk INTEGER, book TEXT, away_ml INTEGER, home_ml INTEGER, ou_line REAL,
    fetched_at TEXT, PRIMARY KEY (game_pk, book));
CREATE TABLE IF NOT EXISTS picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, game_pk INTEGER, game_date TEXT,
    pick_team TEXT, pick_side TEXT, ml INTEGER, my_prob REAL, implied_prob REAL,
    edge REAL, conviction TEXT, units REAL, result TEXT, profit_loss REAL, created_at TEXT, bet INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS bullpen (
    game_pk INTEGER, side TEXT, era REAL, whip REAL, k9 REAL, PRIMARY KEY (game_pk, side));
CREATE TABLE IF NOT EXISTS umpires (
    game_pk INTEGER PRIMARY KEY, hp_name TEXT, hp_id INTEGER, run_factor REAL);
"""

def db_is_ok(path):
    if not path.exists():
        return False
    try:
        c = sqlite3.connect(path)
        ok = c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        c.close()
        return ok
    except Exception:
        return False

def main():
    print(f"Checking {DB} ...")
    if db_is_ok(DB):
        print("  DB opens cleanly (integrity ok). No repair needed.")
        print("  If it was just locked earlier, closing the app resolved it.")
        return

    print("  DB is missing or malformed -- repairing.")
    if not CSV.exists():
        print(f"  ERROR: {CSV.name} not found; cannot restore pick history. Aborting.")
        sys.exit(1)

    # Back up whatever is there (never delete originals)
    if DB.exists():
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = DB.with_suffix(f".db.corrupt-{ts}")
        try:
            shutil.copy2(DB, bak)
            print(f"  Backed up corrupt DB -> {bak.name}")
        except Exception as e:
            print(f"  WARNING: could not back up ({e}). Is the app still open? Aborting.")
            sys.exit(1)
        # remove stale journal if present
        for j in (DB.with_suffix(".db-journal"), DB.with_suffix(".db-wal")):
            try:
                if j.exists(): j.unlink()
            except Exception:
                pass
        try:
            DB.unlink()
        except Exception as e:
            print(f"  ERROR: cannot replace {DB.name} ({e}). Close the app holding it, then retry.")
            sys.exit(1)

    # Build fresh
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    with open(CSV, newline="") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)
    for r in rows:
        con.execute(
            "INSERT INTO picks(game_date,pick_team,ml,conviction,units,result,profit_loss) "
            "VALUES(?,?,?,?,?,?,?)",
            (r["game_date"], r["pick_team"], int(r["ml"]), r["conviction"],
             float(r["units"]), r["result"], float(r["profit_loss"])))
    con.commit()

    ok  = con.execute("PRAGMA integrity_check").fetchone()[0]
    n   = con.execute("SELECT COUNT(*) FROM picks").fetchone()[0]
    w   = con.execute("SELECT COUNT(*) FROM picks WHERE result='W'").fetchone()[0]
    l   = con.execute("SELECT COUNT(*) FROM picks WHERE result='L'").fetchone()[0]
    pl  = con.execute("SELECT ROUND(SUM(profit_loss),3) FROM picks").fetchone()[0]
    con.close()
    print(f"  Rebuilt mlb.db  |  integrity: {ok}  |  picks: {n} ({w}W-{l}L, {pl}u)")
    print("  Daily tables (games/starters/odds/bullpen/umpires) are empty -- your next")
    print("  data pull will repopulate them. Repair complete.")

if __name__ == "__main__":
    main()
