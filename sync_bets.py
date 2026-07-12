#!/usr/bin/env python3
"""
sync_bets.py -- Import your dashboard bet selections into the picks database.

The dashboard's "My Bets" tab has a "Save my bets to file" button that downloads
my_bets.json. Run this to write those selections (and the dollar amount you
staked) into the picks.bet / picks.bet_amount columns so the tracker reflects
them permanently across days and devices.

Usage:
    python sync_bets.py                 # looks for ./my_bets.json (and Downloads)
    python sync_bets.py path/to/my_bets.json

The exported file is the COMPLETE current selection, so this resets every pick's
bet flag/amount to 0 and sets them only for the picks listed. Parlay selections
are tracked in the browser/JSON only (they are not individual picks rows).
"""
import sys, json, sqlite3
from pathlib import Path

P = Path(__file__).parent
DB_DEFAULT = P / "data" / "mlb.db"


def _ensure_cols(con):
    cols = [r[1] for r in con.execute("PRAGMA table_info(picks)")]
    if "bet" not in cols:
        con.execute("ALTER TABLE picks ADD COLUMN bet INTEGER DEFAULT 0")
    if "bet_amount" not in cols:
        con.execute("ALTER TABLE picks ADD COLUMN bet_amount REAL DEFAULT 0")


def apply(db_path, json_path):
    """Set picks.bet / picks.bet_amount from a my_bets.json export.
    Returns (matched, missed_list). Backward-compatible with v1 exports."""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    picks = data.get("picks", [])
    con = sqlite3.connect(str(db_path))
    _ensure_cols(con)
    con.execute("UPDATE picks SET bet=0, bet_amount=0")
    matched, missed, parlays = 0, [], 0
    for p in picks:
        if p.get("type") == "parlay":
            parlays += 1
            continue  # parlays aren't single picks rows; tracked in the JSON only
        try:
            amt = float(p.get("amount") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        cur = con.execute(
            "UPDATE picks SET bet=1, bet_amount=? WHERE game_date=? AND pick_team=? AND ml=?",
            (amt, p.get("date"), p.get("team"), int(p.get("ml"))),
        )
        if cur.rowcount:
            matched += cur.rowcount
        else:
            missed.append(p.get("pid"))
    con.commit()
    con.close()
    if parlays:
        print(f"  [sync_bets] {parlays} parlay selection(s) kept in JSON (not written to picks table).")
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
    print(f"  [sync_bets] {jp.name}: flagged {matched} picks as bet=1 (with amounts).")
    if missed:
        print(f"  [sync_bets] {len(missed)} selection(s) had no DB match (likely today's "
              f"unlogged picks) -- they'll match once results are logged: {missed}")


if __name__ == "__main__":
    main()
