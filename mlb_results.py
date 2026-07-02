"""
mlb_results.py — Automatic result logging + pick record tracker

Usage:
    python mlb_results.py                    # log yesterday's results
    python mlb_results.py --date 2026-06-28  # log a specific date
    python mlb_results.py --record           # print full pick record
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sqlite3, argparse
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

from mlb_data import DB_PATH, _mlb_get

# ── fetch actual scores ───────────────────────────────────────────────────────

def fetch_final_scores(game_date: str) -> list[dict]:
    """
    Pull final scores for a given date from MLB Stats API.
    Returns list of {away_team, home_team, away_score, home_score, away_win}
    """
    try:
        data = _mlb_get("schedule", {
            "sportId":  1,
            "date":     game_date,
            "gameType": "R",
            "fields":   "dates,games,gamePk,status,detailedState,teams,away,home,score,team,name",
        })
        results = []
        for d in data.get("dates", []):
            for g in d.get("games", []):
                status = g.get("status", {}).get("detailedState", "")
                if status not in ("Final", "Completed Early"):
                    continue
                away = g["teams"]["away"]
                home = g["teams"]["home"]
                away_score = away.get("score", 0)
                home_score = home.get("score", 0)
                results.append({
                    "away_team":  away["team"]["name"],
                    "home_team":  home["team"]["name"],
                    "away_score": away_score,
                    "home_score": home_score,
                    "away_win":   1 if away_score > home_score else 0,
                })
        return results
    except Exception as e:
        print(f"  [Results] Score fetch failed: {e}")
        return []


# ── match pick to game result ─────────────────────────────────────────────────

def resolve_pick(pick: dict, scores: list[dict]) -> tuple[str | None, float]:
    """
    Match a pick row to a final score. Returns (result, profit_loss).
    result: 'W', 'L', or None if no match found.
    """
    pick_team = pick["pick_team"]
    pick_side = pick["pick_side"]   # 'away' or 'home'
    ml        = pick["ml"]
    units     = pick["units"]

    for g in scores:
        # Match by team name on the correct side
        team_in_game = g[f"{pick_side}_team"]
        if team_in_game.lower() == pick_team.lower() or pick_team.lower() in team_in_game.lower():
            won = (pick_side == "away" and g["away_win"] == 1) or \
                  (pick_side == "home" and g["away_win"] == 0)
            if won:
                pl = (ml / 100) * units if ml > 0 else (100 / abs(ml)) * units
                return "W", round(pl, 3)
            else:
                return "L", round(-units, 3)

    return None, 0.0


# ── auto log results ──────────────────────────────────────────────────────────

def auto_log_results(game_date: str = None, verbose: bool = True) -> dict:
    """
    Automatically fetch scores and mark pending picks as W/L.
    Returns summary dict.
    """
    game_date = game_date or (date.today() - timedelta(days=1)).isoformat()

    con = sqlite3.connect(DB_PATH)
    pending = pd.read_sql(
        "SELECT * FROM picks WHERE game_date=? AND result IS NULL ORDER BY id",
        con, params=(game_date,)
    )
    con.close()

    if pending.empty:
        if verbose: print(f"No pending picks for {game_date}.")
        return {"date": game_date, "resolved": 0, "wins": 0, "losses": 0, "pl": 0.0}

    if verbose: print(f"\nAuto-logging results for {game_date} ({len(pending)} picks)...")

    scores = fetch_final_scores(game_date)
    if not scores:
        if verbose: print("  No final scores available yet — check back later.")
        return {"date": game_date, "resolved": 0, "wins": 0, "losses": 0, "pl": 0.0}

    if verbose: print(f"  Found {len(scores)} final games.")

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    wins = losses = 0
    total_pl = 0.0
    resolved = 0

    for _, pick in pending.iterrows():
        result, pl = resolve_pick(pick.to_dict(), scores)
        ml = pick["ml"]
        ml_s = f"+{ml}" if ml > 0 else str(ml)

        if result is None:
            if verbose:
                print(f"  ? {pick['pick_team']} {ml_s} ({pick['conviction']}) — no matching final score found")
            continue

        cur.execute(
            "UPDATE picks SET result=?, profit_loss=? WHERE id=?",
            (result, pl, int(pick["id"]))
        )
        resolved += 1
        total_pl += pl
        if result == "W":
            wins += 1
            if verbose: print(f"  W  {pick['pick_team']} {ml_s} ({pick['conviction']}) | +{pl:.2f}u")
        else:
            losses += 1
            if verbose: print(f"  L  {pick['pick_team']} {ml_s} ({pick['conviction']}) | {pl:.2f}u")

    con.commit()
    con.close()

    if verbose:
        print(f"\n  {game_date}: {wins}W-{losses}L | P/L: {total_pl:+.2f}u")

    return {"date": game_date, "resolved": resolved,
            "wins": wins, "losses": losses, "pl": total_pl}


# ── pick record summary ───────────────────────────────────────────────────────

def _bet_filter(con, bets_only):
    """Return ' AND bet=1' if bets_only and the column exists, else ''. """
    if not bets_only:
        return ""
    cols = [r[1] for r in con.execute("PRAGMA table_info(picks)")]
    return " AND bet=1" if "bet" in cols else " AND 1=0"


def get_pick_record(bets_only: bool = False) -> dict:
    """
    Pull full pick record from DB. Returns summary + by-conviction breakdown.
    """
    con = sqlite3.connect(DB_PATH)
    _bf = _bet_filter(con, bets_only)
    df  = pd.read_sql(
        f"SELECT * FROM picks WHERE result IS NOT NULL{_bf} ORDER BY game_date",
        con
    )
    pending_count = pd.read_sql(
        "SELECT COUNT(*) as n FROM picks WHERE result IS NULL", con
    ).iloc[0]["n"]
    con.close()

    if df.empty:
        return {"total": {}, "by_conviction": {}, "by_month": [], "pending": int(pending_count)}

    # Overall
    wins   = int((df["result"] == "W").sum())
    losses = int((df["result"] == "L").sum())
    pushes = int((df["result"] == "P").sum())
    total  = wins + losses
    pl     = float(df["profit_loss"].sum())
    roi    = pl / float(df["units"].sum()) if df["units"].sum() > 0 else 0

    overall = {
        "wins": wins, "losses": losses, "pushes": pushes,
        "total": total, "pl": round(pl, 2), "roi": round(roi, 4),
        "win_pct": round(wins / total, 4) if total else 0,
    }

    # By conviction tier
    by_conv = {}
    for conv, grp in df.groupby("conviction"):
        w = int((grp["result"] == "W").sum())
        l = int((grp["result"] == "L").sum())
        t = w + l
        by_conv[conv] = {
            "wins": w, "losses": l, "total": t,
            "win_pct": round(w/t, 4) if t else 0,
            "pl": round(float(grp["profit_loss"].sum()), 2),
        }

    # By month
    df["month"] = df["game_date"].str[:7]
    by_month = []
    for month, grp in df.groupby("month"):
        w = int((grp["result"] == "W").sum())
        l = int((grp["result"] == "L").sum())
        t = w + l
        by_month.append({
            "month": month, "wins": w, "losses": l,
            "pl": round(float(grp["profit_loss"].sum()), 2),
            "win_pct": round(w/t, 4) if t else 0,
        })

    return {
        "total":         overall,
        "by_conviction": by_conv,
        "by_month":      by_month,
        "pending":       int(pending_count),
    }


def get_bankroll_data(starting_bankroll: float = 500.0, unit_dollars: float = 25.0, bets_only: bool = False) -> dict:
    """
    Compute bankroll curve from resolved picks.

    Args:
        starting_bankroll: Starting dollar amount (default $500)
        unit_dollars:      Dollar value of 1 unit (default $25 = 5% of $500)

    Returns dict with:
        starting       - starting bankroll
        current        - current bankroll
        peak           - highest bankroll reached
        unit_dollars   - dollar value per unit
        total_pl_units - total P/L in units
        total_pl_dollars - total P/L in dollars
        roi_pct        - ROI as fraction (0.12 = 12%)
        history        - list of {date, label, result, units, pl_units, pl_dollars,
                                   bankroll, conviction, ml} per resolved pick
        daily          - list of {date, bankroll} daily snapshots for chart
        bets           - total resolved bets
        wins / losses  - counts
    """
    con = sqlite3.connect(DB_PATH)
    _bf = _bet_filter(con, bets_only)
    df = pd.read_sql(
        f"SELECT * FROM picks WHERE result IS NOT NULL{_bf} ORDER BY game_date, id",
        con
    )
    con.close()

    history = []
    bankroll = starting_bankroll
    peak = starting_bankroll
    daily_snapshots = [{"date": "Start", "bankroll": round(starting_bankroll, 2)}]
    last_date = None

    for _, row in df.iterrows():
        pl_units = float(row["profit_loss"])
        pl_dollars = round(pl_units * unit_dollars, 2)
        bankroll = round(bankroll + pl_dollars, 2)
        peak = max(peak, bankroll)

        ml = int(row["ml"]) if row["ml"] else 0
        ml_s = f"+{ml}" if ml > 0 else str(ml)

        try:
            _bet = int(row["bet"]) if "bet" in row.index and row["bet"] is not None else 0
        except Exception:
            _bet = 0
        history.append({
            "date":       row["game_date"],
            "team":       row["pick_team"],
            "ml":         ml,
            "bet":        _bet,
            "label":      f"{row['pick_team']} {ml_s}",
            "result":     row["result"],
            "conviction": row["conviction"],
            "units":      float(row["units"]),
            "pl_units":   round(pl_units, 3),
            "pl_dollars": pl_dollars,
            "bankroll":   bankroll,
        })

        # Daily snapshot: record once per date
        if row["game_date"] != last_date:
            daily_snapshots.append({"date": row["game_date"], "bankroll": bankroll})
            last_date = row["game_date"]
        else:
            daily_snapshots[-1]["bankroll"] = bankroll  # update same-day

    wins   = int((df["result"] == "W").sum()) if not df.empty else 0
    losses = int((df["result"] == "L").sum()) if not df.empty else 0
    total_pl_units   = round(float(df["profit_loss"].sum()), 3) if not df.empty else 0.0
    total_pl_dollars = round(total_pl_units * unit_dollars, 2)
    roi = total_pl_dollars / starting_bankroll

    return {
        "starting":          starting_bankroll,
        "current":           bankroll,
        "peak":              peak,
        "unit_dollars":      unit_dollars,
        "total_pl_units":    total_pl_units,
        "total_pl_dollars":  total_pl_dollars,
        "roi_pct":           round(roi, 4),
        "bets":              len(history),
        "wins":              wins,
        "losses":            losses,
        "history":           history,
        "daily":             daily_snapshots,
    }


def print_pick_record():
    """Print full pick record to console."""
    rec = get_pick_record()
    t   = rec["total"]

    if not t:
        print("No resolved picks yet.")
        return

    print("\n" + "=" * 55)
    print("  MLB MODEL -- ACTUAL PICK RECORD")
    print("=" * 55)
    print(f"  Overall:  {t['wins']}W - {t['losses']}L  ({t['win_pct']:.1%})  "
          f"| P/L: {t['pl']:+.2f}u  ROI: {t['roi']:+.1%}")
    print(f"  Pending:  {rec['pending']} unresolved picks")

    print("\n  By Conviction:")
    for conv in ["HIGH", "MED-HIGH", "MEDIUM", "LEAN"]:
        if conv in rec["by_conviction"]:
            c = rec["by_conviction"][conv]
            print(f"    {conv:10s}  {c['wins']}W-{c['losses']}L  "
                  f"({c['win_pct']:.1%})  P/L: {c['pl']:+.2f}u")

    if rec["by_month"]:
        print("\n  By Month:")
        for m in rec["by_month"]:
            print(f"    {m['month']}  {m['wins']}W-{m['losses']}L  "
                  f"({m['win_pct']:.1%})  P/L: {m['pl']:+.2f}u")
    print()


# -- main ----------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",   default=None, help="Date to log (YYYY-MM-DD), default yesterday")
    parser.add_argument("--record", action="store_true", help="Print full pick record")
    args = parser.parse_args()

    if args.record:
        print_pick_record()
    else:
        auto_log_results(args.date)
        print()
        print_pick_record()
