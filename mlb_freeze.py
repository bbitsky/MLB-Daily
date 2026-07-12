"""mlb_freeze.py -- Freeze the day's picks at the initial run so they never change.

Rule (established 2026-07-05): the daily picks are locked by the FIRST pick-
generating run of the day. Every later dashboard rebuild reloads that snapshot
instead of recomputing against live odds. Live/current odds live in their own
read-only dashboard tab and never feed the Picks tab.

Usage:
    import mlb_freeze
    # in a pick generator (build_julyN.py / mlb_daily.py):
    picks = mlb_freeze.load_or_freeze(picks, today, base_dir)   # first run saves; re-runs reload
    # in a dashboard rebuild (run_daily.py):
    picks = mlb_freeze.load_frozen(today, base_dir) or []       # never recompute
"""
from __future__ import annotations
import json, os
from datetime import date as _date


def freeze_path(day=None, base_dir="."):
    day = day or _date.today().isoformat()
    return os.path.join(str(base_dir), f"picks_frozen_{day}.json")


def is_frozen(day=None, base_dir="."):
    return os.path.exists(freeze_path(day, base_dir))


def _sanitize(o):
    # Make numpy / Decimal / odd types JSON-safe without importing numpy.
    if hasattr(o, "item"):          # numpy scalar
        try:
            return o.item()
        except Exception:
            pass
    if hasattr(o, "__float__"):
        try:
            return float(o)
        except Exception:
            pass
    return str(o)


def save_frozen(picks, day=None, base_dir=".", meta=None):
    """Write the locked picks + a timestamp/entry-odds snapshot. Returns path."""
    day = day or _date.today().isoformat()
    path = freeze_path(day, base_dir)
    payload = {
        "date": day,
        "frozen_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "meta": meta or {},
        # entry-odds snapshot keyed by matchup, for the Live Odds / CLV tab
        "entry_odds": {f"{g.get('away_team')}@{g.get('home_team')}":
                       {"away_ml": g.get("away_ml"), "home_ml": g.get("home_ml"),
                        "ou_line": g.get("ou_line")}
                       for g in picks},
        "picks": picks,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, default=_sanitize, indent=2)
    return path


def load_frozen(day=None, base_dir="."):
    """Return the frozen picks list for the day, or None if not frozen yet."""
    path = freeze_path(day, base_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("picks")
    except Exception:
        return None


def load_frozen_payload(day=None, base_dir="."):
    """Return the full frozen payload (picks + entry_odds + meta), or None."""
    path = freeze_path(day, base_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_or_freeze(picks, day=None, base_dir=".", meta=None, refresh=False):
    """For pick GENERATORS: first run of the day saves the snapshot and returns
    the freshly computed picks; any later run returns the frozen picks unchanged
    (so daily picks never change from the initial run). Pass refresh=True to
    deliberately re-lock with new picks.
    """
    day = day or _date.today().isoformat()
    if not refresh and is_frozen(day, base_dir):
        frozen = load_frozen(day, base_dir)
        if frozen is not None:
            print(f"  [freeze] picks already locked for {day} "
                  f"({freeze_path(day, base_dir)}) — reloading, not recomputing. "
                  f"Use refresh=True / --refresh to override.")
            return frozen
    path = save_frozen(picks, day, base_dir, meta=meta)
    print(f"  [freeze] locked {len(picks)} games -> {os.path.basename(path)}")
    return picks


if __name__ == "__main__":
    demo = [{"away_team": "Brewers", "home_team": "Diamondbacks",
             "away_ml": -124, "home_ml": 104, "ou_line": 8.5, "home_units": 0.5}]
    import tempfile
    d = tempfile.mkdtemp()
    p1 = load_or_freeze(demo, "2026-07-05", d)           # writes
    demo2 = [dict(demo[0], home_ml=118)]                 # "line moved"
    p2 = load_or_freeze(demo2, "2026-07-05", d)          # reloads original
    assert p2[0]["home_ml"] == 104, "freeze failed to lock"
    print("OK freeze locks initial picks:", p2[0]["home_ml"])
