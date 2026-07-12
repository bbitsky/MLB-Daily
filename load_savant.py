"""load_savant.py -- Baseball Savant (Statcast) data for the pipeline.

Savant is MLB's official site and is NOT scrape-blocked like FanGraphs, so this
pulls the leaderboard CSV endpoints directly. If the live call fails (offline, or
a temporary block), it falls back to any Savant CSV you've DOWNLOADED into the
project folder (click "Download CSV" on the leaderboard). Everything degrades to
{} so the pipeline never breaks.

Provides:
  pitcher_xstats(season) -> {normalized_name: {"xera","xwoba","xba"}}
  team_oaa(season)       -> {team_full_name: {"def_rating"(OAA), "def_rank"}}

Refresh: nothing to do if the live pull works. To force offline data, download:
  Expected Statistics -> Pitcher  -> save as savant_pitching*.csv
  Outs Above Average              -> save as savant_oaa*.csv
"""
from io import StringIO
from pathlib import Path
import pandas as pd

try:
    import requests
except Exception:
    requests = None

P = Path(__file__).parent
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_CACHE = {}

_EXP_URL = ("https://baseballsavant.mlb.com/leaderboard/expected_statistics"
            "?type=pitcher&year={yr}&position=&team=&filterType=bip&min=1&csv=true")
_OAA_URL = ("https://baseballsavant.mlb.com/leaderboard/outs_above_average"
            "?type=Fielder&startYear={yr}&endYear={yr}&split=no&team=&range=year"
            "&min=1&pos=&roles=&viz=hide&csv=true")


def _fetch_csv(url):
    if requests is None:
        return None
    try:
        r = requests.get(url, headers={"User-Agent": _UA}, timeout=25)
        r.raise_for_status()
        if "," not in r.text[:2000]:      # not a CSV (probably an HTML shell)
            return None
        return pd.read_csv(StringIO(r.text))
    except Exception:
        return None


def _read_local(*patterns):
    for pat in patterns:
        hits = sorted(P.glob(pat))
        if hits:
            try:
                return pd.read_csv(hits[-1])
            except Exception:
                pass
    return None


def _filter_year(df, season):
    """Keep only rows for the requested season if a year column exists."""
    if df is None:
        return None
    yc = _col(df, "year", "season")
    if yc is None:
        return df
    try:
        return df[df[yc].astype(str).str.strip() == str(int(season))]
    except Exception:
        return df


def _norm_name(s):
    return " ".join(str(s).lower().replace(".", "").split())


def _col(df, *cands):
    low = {str(c).strip().lower(): c for c in df.columns}
    for c in cands:
        if c in low:
            return low[c]
    return None


def _name_series(df):
    """Savant CSVs use either a combined ' last_name, first_name' column or two."""
    ln = _col(df, "last_name", "last name")
    fn = _col(df, "first_name", "first name")
    if ln and fn:
        return (df[fn].astype(str).str.strip() + " " + df[ln].astype(str).str.strip())
    pn = _col(df, "player_name", "name", " last_name, first_name", "last_name, first_name")
    if pn:
        # "Last, First" -> "First Last"
        def flip(x):
            x = str(x)
            return (x.split(",")[1].strip() + " " + x.split(",")[0].strip()) if "," in x else x
        return df[pn].map(flip)
    return None


def pitcher_xstats(season):
    key = ("pit", season)
    if key in _CACHE:
        return _CACHE[key]
    df = _read_local(f"savant_pitch*{season}*.csv", f"*expected_statistics*{season}*.csv",
                     "savant_pitch*.csv", "savant*pitching*.csv", "*expected_statistics*pitch*.csv")
    df = _filter_year(df, season)
    if df is None or df.empty:
        df = _filter_year(_fetch_csv(_EXP_URL.format(yr=season)), season)
    out = {}
    if df is not None and not df.empty:
        names = _name_series(df)
        xwoba = _col(df, "est_woba", "xwoba", "est_woba_using_speedangle")
        xba   = _col(df, "est_ba", "xba", "est_ba_using_speedangle")
        xera  = _col(df, "xera", "est_era")
        if names is not None:
            for i, nm in names.items():
                rec = {}
                if xwoba is not None: rec["xwoba"] = _f(df.at[i, xwoba])
                if xba   is not None: rec["xba"]   = _f(df.at[i, xba])
                if xera  is not None: rec["xera"]  = _f(df.at[i, xera])
                if rec:
                    out[_norm_name(nm)] = rec
            print(f"  [Savant] pitcher xstats loaded for {len(out)} pitchers ({season}).")
    _CACHE[key] = out
    return out


# Savant abbrev -> MLB full name (OAA CSV uses team abbreviations)
_SV_TO_FULL = {
    "AZ": "Arizona Diamondbacks", "ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles", "BOS": "Boston Red Sox", "CHC": "Chicago Cubs",
    "CWS": "Chicago White Sox", "CHW": "Chicago White Sox", "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians", "COL": "Colorado Rockies", "DET": "Detroit Tigers",
    "HOU": "Houston Astros", "KC": "Kansas City Royals", "LAA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers", "MIA": "Miami Marlins", "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins", "NYM": "New York Mets", "NYY": "New York Yankees",
    "OAK": "Athletics", "ATH": "Athletics", "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates", "SD": "San Diego Padres", "SF": "San Francisco Giants",
    "SEA": "Seattle Mariners", "STL": "St. Louis Cardinals", "TB": "Tampa Bay Rays",
    "TEX": "Texas Rangers", "TOR": "Toronto Blue Jays", "WSH": "Washington Nationals",
    "WSN": "Washington Nationals",
}

# Savant OAA "display_team_name" gives nicknames -> full names
_NICK_TO_FULL = {
    "Diamondbacks": "Arizona Diamondbacks", "D-backs": "Arizona Diamondbacks",
    "Braves": "Atlanta Braves", "Orioles": "Baltimore Orioles", "Red Sox": "Boston Red Sox",
    "Cubs": "Chicago Cubs", "White Sox": "Chicago White Sox", "Reds": "Cincinnati Reds",
    "Guardians": "Cleveland Guardians", "Rockies": "Colorado Rockies", "Tigers": "Detroit Tigers",
    "Astros": "Houston Astros", "Royals": "Kansas City Royals", "Angels": "Los Angeles Angels",
    "Dodgers": "Los Angeles Dodgers", "Marlins": "Miami Marlins", "Brewers": "Milwaukee Brewers",
    "Twins": "Minnesota Twins", "Mets": "New York Mets", "Yankees": "New York Yankees",
    "Athletics": "Athletics", "Phillies": "Philadelphia Phillies", "Pirates": "Pittsburgh Pirates",
    "Padres": "San Diego Padres", "Giants": "San Francisco Giants", "Mariners": "Seattle Mariners",
    "Cardinals": "St. Louis Cardinals", "Rays": "Tampa Bay Rays", "Rangers": "Texas Rangers",
    "Blue Jays": "Toronto Blue Jays", "Nationals": "Washington Nationals",
}


def team_oaa(season):
    key = ("oaa", season)
    if key in _CACHE:
        return _CACHE[key]
    df = _read_local(f"savant_oaa*{season}*.csv", f"*outs_above_average*{season}*.csv",
                     "savant_oaa*.csv", "*outs_above_average*.csv")
    df = _filter_year(df, season)
    if df is None or df.empty:
        df = _filter_year(_fetch_csv(_OAA_URL.format(yr=season)), season)
    out = {}
    if df is not None and not df.empty:
        tcol = _col(df, "team", "team_name", "display_team_name", "team_abbrev", "entity_name")
        ocol = _col(df, "outs_above_average", "oaa", "fielding_runs_prevented")
        if tcol and ocol:
            agg = {}
            for i in range(len(df)):
                tm = str(df.at[df.index[i], tcol]).strip()
                full = _NICK_TO_FULL.get(tm) or _SV_TO_FULL.get(tm.upper())
                v = _f(df.at[df.index[i], ocol])
                if full and v is not None:   # skip "---" (traded/multi-team rows)
                    agg[full] = agg.get(full, 0.0) + v
            ranked = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
            for r, (tm, v) in enumerate(ranked):
                out[tm] = {"def_rating": round(v, 1), "def_rank": r + 1}
            print(f"  [Savant] team OAA loaded for {len(out)} teams ({season}).")
    _CACHE[key] = out
    return out


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    import sys
    yr = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    px = pitcher_xstats(yr); oa = team_oaa(yr)
    print("pitchers:", list(px.items())[:2])
    print("oaa:", list(oa.items())[:3])
