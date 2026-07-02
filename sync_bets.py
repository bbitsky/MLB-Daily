#!/usr/bin/env python3
"""
sync_bets.py -- Import your dashboard bet selections into the picks database.

The dashboard's "My Bets" tab has a "Save my bets to file" button that downloads
my_bets.json. Run this to write those selections into the picks.bet column so the
tracker reflects them permanently (across days and devices).

Usage:
    python sync_bets.py                 # looks for ./my_bets.json (and Downloads)
    python sync_bets.py path/to/my_bets.json

The exported file is the COMPLETE current selection, so this resets every pick's
bet flag to 0 and sets bet=1 only for the picks listed.
"""
import sys, json, sqlite3
from pathlib import Path

P = Path(__file__).parent
DB_DEFAULT = P / "data" / "mlb.db"


def _ensure_bet_column(con):
    cols = [r[1] for r in con.execute("PRAGMA table_info(picks)")]
    if "bet" not in cols:
        con.execute("ALTER TABLE picks ADD COLUMN bet INTEGER DEFAULT 0")


def apply(db_path, json_path):
    """Set picks.bet from a my_bets.json export. Returns (matched, missed_list)."""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    picks = data.get("picks", [])
    con = sqlite3.connect(str(db_path))
    _ensure_bet_column(con)
    con.execute("UPDATE picks SET bet=0")
    matched, missed = 0, []
    for p in picks:
        # match on date + team + moneyline (the stable pick identity)
        cur = con.execute(
            "UPDATE picks SET bet=1 WHERE game_date=? AND pick_team=? AND ml=?",
            (p.get("date"), p.get("team"), int(p.get("ml"))),
        )
        if cur.rowcount:
            matched += cur.rowcount
        else:
            missed.append(p.get("pid"))
    con.commit()
    con.close()
    return matched, missed


def _find_json(arg):
    if arg:
        return Path(arg)
    for cand in [P / "my_bets.json", Path.home() / "Downloads" / "my_bets.json"]:
        if cand.exists():
            return cand
    return P / "my_bets.json"


def main():
    jp = _find_json(sys.argv[1] if len(sys.argv) > 1 else None)
    if not jp.exists():
        print(f"  [sync_bets] No selection file found ({jp}). Nothing to do.")
        return
    if not DB_DEFAULT.exists():
        print(f"  [sync_bets] DB not found at {DB_DEFAULT}. Run repair_mlb_db.py first.")
        sys.exit(1)
    matched, missed = apply(DB_DEFAULT, jp)
    print(f"  [sync_bets] {jp.name}: flagged {matched} picks as bet=1.")
    if missed:
        print(f"  [sync_bets] {len(missed)} selection(s) had no DB match (likely today's "
              f"unlogged picks) -- they'll match once results are logged: {missed}")


if __name__ == "__main__":
    main()
