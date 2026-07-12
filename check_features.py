"""
check_features.py — Diagnose why the trained model has fewer features than expected.

Reads the SAME live DB the trainer uses (mlb_data.DB_PATH), reports which feature
columns exist and how many rows are populated, lists tables, and prints the active
feature count of the saved model. Run:  python check_features.py
"""
import sqlite3
from pathlib import Path

import mlb_data as m

DB = str(m.DB_PATH)
print(f"DB: {DB}")
con = sqlite3.connect(DB)
cur = con.cursor()

# Tables present
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables:", tables)

# games columns + total
games_cols = [r[1] for r in cur.execute("PRAGMA table_info(games)")]
total = cur.execute("SELECT COUNT(*) FROM games").fetchone()[0]
print(f"total games: {total}")

# Seasons in the games table
try:
    seasons = [r[0] for r in cur.execute("SELECT DISTINCT season FROM games ORDER BY season")]
    print("seasons:", seasons)
except Exception as e:
    print("seasons: (error)", e)

# Non-null counts for the mlb_backfill feature columns (these ARE games columns)
print("\n-- games feature columns (from mlb_backfill) --")
for col in ["away_streak", "home_streak", "is_day_game",
            "away_ops", "home_ops", "away_def_rank", "home_def_rank"]:
    if col in games_cols:
        n = cur.execute(f"SELECT COUNT(*) FROM games WHERE {col} IS NOT NULL").fetchone()[0]
        print(f"  {col:16s} populated: {n}/{total}")
    else:
        print(f"  {col:16s} COLUMN MISSING (run mlb_backfill.py)")

# Bullpen lives in its own table (joined at load time)
print("\n-- bullpen table (from backfill_bullpen) --")
if "bullpen" in tables:
    bcols = [r[1] for r in cur.execute("PRAGMA table_info(bullpen)")]
    brows = cur.execute("SELECT COUNT(*) FROM bullpen").fetchone()[0]
    print(f"  bullpen rows: {brows}  cols: {bcols}")
else:
    print("  bullpen table MISSING (run backfill_bullpen.py)")

con.close()

# What the trained model actually carries
print("\n-- saved model --")
try:
    import joblib
    obj = joblib.load(Path(__file__).parent / "data" / "mlb_model.pkl")
    if isinstance(obj, dict):
        feats = obj.get("features", [])
        print(f"  active features ({len(feats)}): {feats}")
    else:
        print("  legacy model format (no feature list stored)")
except Exception as e:
    print("  could not load model:", e)
