"""load_bref.py -- Load Baseball-Reference exports (team OPS+, Rdrs, FIP) into the
pipeline so FanGraphs is not needed for team-level advanced stats.

HOW TO REFRESH THE DATA (do this ~weekly to stay current):
  On Baseball-Reference's 2026 pages, use "Share & Export -> Get table as
  Excel Workbook" (or CSV) and save into this folder. Any of these name
  patterns are auto-detected:
    *batting.xls / *batting*.csv    -> Team Standard Batting  (OPS, OPS+)
    *fielding.xls / *fielding*.csv  -> Team Standard Fielding (Rdrs, Fld%)
    *pitching.xls / *pitching*.csv  -> Team Standard Pitching (FIP, ERA+)
  (BR's .xls export is really an HTML table; pandas.read_html handles it.)

The pipeline uses this data first and falls back to the MLB Stats API if a file
is missing. Per-pitcher FIP comes from the MLB Stats API (compute_fip), not here.
"""
from pathlib import Path
import pandas as pd

P = Path(__file__).parent
_CACHE = {}


def _find(*patterns):
    for pat in patterns:
        hits = sorted(P.glob(pat))
        if hits:
            return hits[-1]
    return None


def _read_team_table(path):
    if not path:
        return None
    try:
        tables = pd.read_html(str(path))
        df = max(tables, key=lambda t: t.shape[1])
        if getattr(df.columns, "nlevels", 1) > 1:
            df.columns = [c[-1] for c in df.columns]
        if "Tm" not in df.columns:
            return None
        df = df[df["Tm"].notna()]
        df = df[~df["Tm"].astype(str).str.contains(
            "League|Average|Total|^Tm$", case=False, na=False, regex=True)]
        return df
    except Exception as e:
        print(f"  [BRef] could not read {path.name}: {e}")
        return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_all(verbose=True):
    if _CACHE:
        return _CACHE
    out = {"batting": {}, "fielding": {}, "pitching": {}}

    bat = _read_team_table(_find("*batting.xls", "*batting*.csv"))
    if bat is not None and "OPS+" in bat.columns:
        for _, r in bat.iterrows():
            tm = str(r["Tm"]).strip()
            out["batting"][tm] = {"ops": _num(r.get("OPS")), "ops_plus": _num(r.get("OPS+"))}

    fld = _read_team_table(_find("*fielding.xls", "*fielding*.csv"))
    if fld is not None:
        col = "Rdrs" if "Rdrs" in fld.columns else ("Rtot" if "Rtot" in fld.columns else None)
        if col:
            ranked = [(str(r["Tm"]).strip(), _num(r[col])) for _, r in fld.iterrows()]
            ranked = [(t, v) for t, v in ranked if v is not None]
            ranked.sort(key=lambda x: x[1], reverse=True)   # most runs saved = best
            for i, (tm, v) in enumerate(ranked):
                out["fielding"][tm] = {"def_rating": v, "def_rank": i + 1}

    pit = _read_team_table(_find("*pitching.xls", "*pitching*.csv"))
    if pit is not None and "FIP" in pit.columns:
        for _, r in pit.iterrows():
            tm = str(r["Tm"]).strip()
            out["pitching"][tm] = {"team_fip": _num(r.get("FIP")), "team_era": _num(r.get("ERA"))}

    if verbose:
        print(f"  [BRef] loaded batting={len(out['batting'])} "
              f"fielding={len(out['fielding'])} pitching={len(out['pitching'])} teams")
    _CACHE.clear(); _CACHE.update(out)
    return out


def team_ops_plus(team):
    return (load_all(False)["batting"].get(team) or {}).get("ops_plus")

def def_ranks():
    return load_all(False)["fielding"]

def team_pitching(team):
    return load_all(False)["pitching"].get(team)


if __name__ == "__main__":
    d = load_all()
    for k in ("batting", "fielding", "pitching"):
        sample = list(d[k].items())[:2]
        print(f"  {k}: {sample}")
