# -*- coding: utf-8 -*-
"""
backfill_vs_sp_ops.py — Populate away_vs_sp_ops / home_vs_sp_ops on the games table.

Feature: each team's SEASON OPS vs the OPPOSING starter's handedness.
  away_vs_sp_ops = away team's OPS vs (home starter's throwing hand: L/R)
  home_vs_sp_ops = home team's OPS vs (away starter's throwing hand: L/R)

This is the last historical feature that had no loader, so mlb_train.py always
dropped `vs_sp_ops_diff` as zero-variance. This script mirrors the LIVE daily path
(mlb_data.fetch_today_game_data): team L/R splits via fetch_team_splits() and
starter handedness via the MLB people endpoint.

Prereqs: games + starters populated (run mlb_data.py --build first).
Run:
    python backfill_vs_sp_ops.py --seasons 2018 2019 2020 2021 2022 2023 2024 2025 2026
    # then: python mlb_train.py   (expect 34 active features, vs_sp_ops_diff active)

Safe to re-run: only fills games whose columns are NULL unless --force is given.
Runtime: a few minutes — team splits are cached per (team, season) and pitcher
handedness is cached per pitcher_id (handedness never changes).
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import sqlite3
import time

# Reuse the SAME live DB, team-splits fetch, and API helper the daily path uses.
from mlb_data import DB_PATH, fetch_team_splits, _mlb_get

_HAND_CACHE: dict = {}


def pitcher_hand(pid) -> str:
    """Return 'L' or 'R' for a pitcher_id (default 'R'). Cached; handedness is fixed."""
    if pid is None:
        return "R"
    if pid in _HAND_CACHE:
        return _HAND_CACHE[pid]
    hand = "R"
    try:
        data = _mlb_get(f"people/{pid}", {})
        person = (data.get("people") or [{}])[0]
        hand = person.get("pitchHand", {}).get("code", "R") or "R"
        time.sleep(0.05)  # be polite to the API on cache-miss
    except Exception:
        hand = "R"
    _HAND_CACHE[pid] = hand
    return hand


def add_columns(con):
    cur = con.cursor()
    existing = {r[1] for r in cur.execute("PRAGMA table_info(games)")}
    added = []
    for col in ("away_vs_sp_ops", "home_vs_sp_ops"):
        if col not in existing:
            cur.execute(f"ALTER TABLE games ADD COLUMN {col} REAL")
            added.append(col)
    con.commit()
    print(f"  columns added: {added if added else 'none (already exist)'}")


def _vs_ops(splits: dict, opp_hand: str) -> float:
    key = f"vs_{'lhp' if opp_hand == 'L' else 'rhp'}_ops"
    return splits.get(key, 0.720) or 0.720


def backfill(seasons, force=False):
    con = sqlite3.connect(DB_PATH)
    print(f"DB: {DB_PATH}")
    print(f"Seasons: {seasons}")
    add_columns(con)
    cur = con.cursor()

    total = 0
    for season in seasons:
        where_new = "" if force else \
            "AND (g.away_vs_sp_ops IS NULL OR g.home_vs_sp_ops IS NULL)"
        rows = cur.execute(f"""
            SELECT g.game_pk, g.away_team, g.home_team,
                   sa.pitcher_id AS away_pid, sh.pitcher_id AS home_pid
            FROM games g
            LEFT JOIN starters sa ON g.game_pk=sa.game_pk AND sa.side='away'
            LEFT JOIN starters sh ON g.game_pk=sh.game_pk AND sh.side='home'
            WHERE g.season=? AND g.status='Final' {where_new}
        """, (season,)).fetchall()

        if not rows:
            print(f"  {season}: nothing to update.")
            continue

        print(f"  {season}: {len(rows)} games... ", end="", flush=True)
        batch = []
        for game_pk, away_team, home_team, away_pid, home_pid in rows:
            away_splits = fetch_team_splits(away_team, season)  # cached per team-season
            home_splits = fetch_team_splits(home_team, season)
            away_hand = pitcher_hand(away_pid)
            home_hand = pitcher_hand(home_pid)
            # away team hits vs the HOME starter's hand; home team vs the AWAY starter's hand
            away_vs = _vs_ops(away_splits, home_hand)
            home_vs = _vs_ops(home_splits, away_hand)
            batch.append((away_vs, home_vs, game_pk))

        cur.executemany(
            "UPDATE games SET away_vs_sp_ops=?, home_vs_sp_ops=? WHERE game_pk=?", batch)
        con.commit()
        total += len(batch)
        print(f"updated {len(batch)}.")

    # Quick variance sanity check
    try:
        n_ok = cur.execute(
            "SELECT COUNT(*) FROM games WHERE away_vs_sp_ops IS NOT NULL").fetchone()[0]
        distinct = cur.execute(
            "SELECT COUNT(DISTINCT away_vs_sp_ops) FROM games "
            "WHERE away_vs_sp_ops IS NOT NULL").fetchone()[0]
        print(f"\n  away_vs_sp_ops populated: {n_ok}  (distinct values: {distinct})")
        print(f"  unique pitchers looked up: {len(_HAND_CACHE)}")
    except Exception:
        pass
    con.close()
    print(f"Done. Total games updated: {total}")
    print("Next: python mlb_train.py  (expect vs_sp_ops_diff active -> 34 features)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Backfill vs-SP-handedness team OPS")
    ap.add_argument("--seasons", nargs="+", type=int,
                    default=[2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--force", action="store_true",
                    help="Recompute all rows, not just NULL ones")
    args = ap.parse_args()
    print("vs-SP-handedness OPS backfill")
    print("=" * 50)
    backfill(args.seasons, force=args.force)
