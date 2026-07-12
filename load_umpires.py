"""load_umpires.py -- real home-plate umpire tendencies + daily assignments.

Replaces the placeholder hash-based "grade/zone/O-U lean" in the dashboard with
REAL data you drop into the project folder. Same download-a-CSV pattern as
load_savant.py / load_bref.py; everything degrades to {} so the pipeline never
breaks.

Two inputs (either/both optional):

1. Season tendencies  ->  file matching  umpire*.csv / *umpscorecard*.csv
   Flexible columns (auto-detected, any subset):
     name/umpire, accuracy(_pct), consistency, favor(_home), runs_per_game,
     k_pct, bb_pct, games
   From umpscorecards.com (Umpires table -> download), or any CSV with a name
   column + at least one stat.

2. Today's assignments  ->  file matching  ump_assign*.csv / *assignments*.csv
   Columns (auto-detected): date, away, home, umpire   (date optional)
   OR a single 'matchup' column like "Away@Home" + 'umpire'.

Provides:
  ump_tendencies()            -> {normalized_name: {grade, score, zone, ou_lean, ...raw}}
  todays_assignments(date)    -> {"Away Team@Home Team": "Umpire Name"}
  lookup(name)                -> tendencies record for one ump (or {})
"""
from pathlib import Path
import pandas as pd

P = Path(__file__).parent
_CACHE = {}


def _read_local(*patterns):
    for pat in patterns:
        hits = sorted(P.glob(pat))
        if hits:
            try:
                return pd.read_csv(hits[-1])
            except Exception:
                pass
    return None


def _col(df, *cands):
    low = {str(c).strip().lower().replace(" ", "_"): c for c in df.columns}
    for c in cands:
        c = c.replace(" ", "_")
        if c in low:
            return low[c]
    # loose contains-match fallback
    for c in cands:
        for k, orig in low.items():
            if c.replace(" ", "_") in k:
                return orig
    return None


def _f(v):
    try:
        return float(str(v).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def norm_name(s):
    return " ".join(str(s).lower().replace(".", "").replace(",", " ").split())


def _quartile_grade(value, sorted_vals, higher_is_better=True):
    """A/B/C/D by quartile position of value within sorted_vals."""
    if value is None or not sorted_vals:
        return None
    import bisect
    rank = bisect.bisect_left(sorted(sorted_vals), value)
    pct = rank / max(1, len(sorted_vals) - 1)
    if not higher_is_better:
        pct = 1 - pct
    return "A" if pct >= 0.75 else "B" if pct >= 0.50 else "C" if pct >= 0.25 else "D"


def ump_tendencies():
    """Load per-umpire season tendencies and derive grade/score/zone/O-U lean."""
    if "tend" in _CACHE:
        return _CACHE["tend"]
    df = _read_local("umpire*.csv", "*umpscorecard*.csv", "*umpires*.csv", "ump_stats*.csv")
    out = {}
    if df is not None and not df.empty:
        ncol = _col(df, "umpire", "name", "umpire_name", "official")
        acc  = _col(df, "accuracy", "accuracy_pct", "acc")
        con  = _col(df, "consistency", "consistency_pct")
        fav  = _col(df, "favor", "favor_home", "home_favor", "favor_runs")
        rpg  = _col(df, "runs_per_game", "runs/game", "rpg", "total_runs_per_game")
        kp   = _col(df, "k_pct", "k%", "strikeout_pct")
        bbp  = _col(df, "bb_pct", "bb%", "walk_pct")
        gms  = _col(df, "games", "g", "n_games")
        if ncol is not None:
            acc_vals = [_f(v) for v in df[acc]] if acc else []
            acc_vals = [v for v in acc_vals if v is not None]
            rpg_vals = [_f(v) for v in df[rpg]] if rpg else []
            rpg_vals = [v for v in rpg_vals if v is not None]
            rpg_med  = pd.Series(rpg_vals).median() if rpg_vals else None
            for i in df.index:
                nm = df.at[i, ncol]
                if not str(nm).strip():
                    continue
                rec = {"name": str(nm).strip()}
                a = _f(df.at[i, acc]) if acc else None
                if a is not None: rec["accuracy"] = a
                if con: rec["consistency"] = _f(df.at[i, con])
                if fav: rec["favor"] = _f(df.at[i, fav])
                r = _f(df.at[i, rpg]) if rpg else None
                if r is not None: rec["runs_per_game"] = r
                if kp:  rec["k_pct"]  = _f(df.at[i, kp])
                if bbp: rec["bb_pct"] = _f(df.at[i, bbp])
                if gms: rec["games"]  = _f(df.at[i, gms])
                # Derived, real (not hashed):
                rec["grade"] = _quartile_grade(a, acc_vals, higher_is_better=True) or "B"
                rec["score"] = round(min(10, max(0, (a - 88) / (96 - 88) * 10)), 1) if a is not None else 5.0
                # O/U lean from runs/game vs the loaded median (bigger zone -> fewer runs)
                if r is not None and rpg_med is not None:
                    d = r - rpg_med
                    rec["ou_lean"] = ("Strong over" if d > 0.7 else "Over lean" if d > 0.2
                                      else "Strong under" if d < -0.7 else "Under lean" if d < -0.2
                                      else "Neutral")
                    rec["ou_delta"] = round(d, 2)
                else:
                    rec["ou_lean"] = "Neutral"
                # Zone/favor tilt
                fv = rec.get("favor")
                if fv is not None:
                    rec["zone"] = ("Hitter-friendly" if fv > 0.15 else "Pitcher-friendly"
                                   if fv < -0.15 else "Balanced")
                else:
                    rec["zone"] = "Balanced"
                out[norm_name(nm)] = rec
            print(f"  [Umpires] loaded tendencies for {len(out)} umpires.")
    # Fall back to (and fill gaps with) tendencies derived from our own game log,
    # so the tab has REAL grades/O-U leans even with no dropped-in CSV. CSV wins.
    try:
        for k, v in db_tendencies().items():
            out.setdefault(k, v)
    except Exception:
        pass
    _CACHE["tend"] = out
    return out


def db_tendencies(db_path=None):
    """Per-umpire tendencies computed from our own umpires+games history — no CSV
    or external scrape needed. For each HP umpire with a real sample: games worked,
    avg total runs, O/U lean vs the league, run factor, and a confidence grade.
    Cached; returns {} if the umpires table is empty/unavailable."""
    if "db_tend" in _CACHE:
        return _CACHE["db_tend"]
    out = {}
    rows = []
    try:
        import sqlite3
        dbp = db_path
        if dbp is None:
            from mlb_data import DB_PATH as dbp
        con = sqlite3.connect(str(dbp), timeout=10)
        rows = con.execute("""
            SELECT u.hp_name, g.away_score + g.home_score AS total_runs
            FROM umpires u JOIN games g ON u.game_pk = g.game_pk
            WHERE g.status='Final' AND u.hp_name IS NOT NULL
              AND g.away_score IS NOT NULL AND g.home_score IS NOT NULL
        """).fetchall()
        con.close()
    except Exception:
        rows = []
    from collections import defaultdict
    by = defaultdict(list)
    for nm, tr in rows:
        if nm and tr is not None:
            by[nm].append(tr)
    all_runs = [tr for v in by.values() for tr in v]
    league = (sum(all_runs) / len(all_runs)) if all_runs else 8.6
    for nm, vals in by.items():
        if len(vals) < 10:                      # need a real sample to say anything
            continue
        avg = sum(vals) / len(vals)
        d = avg - league
        rec = {"name": nm, "games": len(vals),
               "runs_per_game": round(avg, 2), "run_factor": round(avg / league, 3),
               "ou_delta": round(d, 2), "source": "gamelog"}
        rec["ou_lean"] = ("Strong over" if d > 0.7 else "Over lean" if d > 0.25
                          else "Strong under" if d < -0.7 else "Under lean" if d < -0.25
                          else "Neutral")
        rec["zone"] = ("Hitter-friendly" if d > 0.4 else "Pitcher-friendly"
                       if d < -0.4 else "Balanced")
        # Grade = confidence the O/U tilt is real (sample size + tilt magnitude).
        ad = abs(d)
        rec["grade"] = ("A" if len(vals) >= 60 and ad >= 0.5 else
                        "B" if len(vals) >= 40 else
                        "C" if len(vals) >= 20 else "D")
        # Score 0-10, pitcher-friendly (under) leans higher.
        rec["score"] = round(max(0.0, min(10.0, 5.0 - d)), 1)
        out[norm_name(nm)] = rec
    if out:
        print(f"  [Umpires] derived tendencies for {len(out)} umpires from game history.")
    _CACHE["db_tend"] = out
    return out


def fill_live_assignments(picks, verbose=True):
    """Populate g['hp_umpire'] for today's games from the MLB Stats API officials
    (live, same-day) when it's missing. Needs each pick to carry a game_pk. Safe
    no-op if mlb_data / the API is unavailable. Returns count filled."""
    try:
        import mlb_data
    except Exception:
        return 0
    n = 0
    for g in picks or []:
        if g.get("hp_umpire"):
            continue
        pk = g.get("game_pk") or g.get("gamePk") or g.get("gamepk")
        if not pk:
            continue
        try:
            info = mlb_data.fetch_umpire_for_game(pk) or {}
            nm = info.get("hp_name")
            if nm and nm != "Unknown":
                g["hp_umpire"] = nm
                n += 1
        except Exception:
            continue
    if verbose and n:
        print(f"  [Umpires] live-assigned {n} HP umpire(s) from MLB API.")
    return n


def todays_assignments(date_iso=None):
    """Map 'Away@Home' -> umpire name for the day (or all rows if no date match)."""
    key = ("assign", date_iso)
    if key in _CACHE:
        return _CACHE[key]
    df = _read_local("ump_assign*.csv", "*assignments*.csv", "ump_today*.csv")
    out = {}
    if df is not None and not df.empty:
        ucol = _col(df, "umpire", "name", "hp_umpire", "official")
        acol = _col(df, "away", "away_team", "visitor")
        hcol = _col(df, "home", "home_team")
        mcol = _col(df, "matchup", "game")
        dcol = _col(df, "date", "game_date")
        if dcol and date_iso:
            try:
                df = df[df[dcol].astype(str).str.strip().str[:10] == date_iso]
            except Exception:
                pass
        if ucol is not None:
            for i in df.index:
                ump = str(df.at[i, ucol]).strip()
                if not ump:
                    continue
                if acol and hcol:
                    k = f"{str(df.at[i, acol]).strip()}@{str(df.at[i, hcol]).strip()}"
                elif mcol:
                    k = str(df.at[i, mcol]).strip().replace(" @ ", "@").replace(" vs ", "@")
                else:
                    continue
                out[k] = ump
            print(f"  [Umpires] loaded {len(out)} assignments"
                  f"{' for '+date_iso if date_iso else ''}.")
    _CACHE[key] = out
    return out


def lookup(name):
    return ump_tendencies().get(norm_name(name), {})


if __name__ == "__main__":
    t = ump_tendencies()
    a = todays_assignments()
    print("tendencies:", list(t.items())[:2] or "none (drop umpire*.csv in folder)")
    print("assignments:", list(a.items())[:3] or "none (drop ump_assign*.csv in folder)")
