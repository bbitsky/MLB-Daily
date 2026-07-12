"""load_odds.py -- Historical MLB moneylines from SportsbookReviewsOnline exports.

Drop the season files in the project folder (any of these name patterns):
    mlb-odds-YYYY.xlsx  /  mlb odds YYYY.xlsx  /  *odds*YYYY*.xls*

Each file is 2 rows per game (visitor 'V' then home 'H') with Open/Close moneylines.
This parses them into per-game closing (and opening) lines, matched by date + teams,
so the backtest can use REAL prices and compute closing-line value (CLV) instead of
a flat -110 assumption.

    closing_odds(season) -> {(date_iso, away_key, home_key): {away_close, home_close,
                                                              away_open, home_open, ...}}
    lookup(date_iso, away_name, home_name) -> that record or None
"""
from pathlib import Path
import pandas as pd

P = Path(__file__).parent
_CACHE = {}

# SportsbookReviewsOnline team codes -> current MLB full names (variants included)
_SBR = {
    "ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves", "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox", "BRS": "Boston Red Sox",
    "CHC": "Chicago Cubs", "CUB": "Chicago Cubs",
    "CIN": "Cincinnati Reds", "CLE": "Cleveland Guardians", "COL": "Colorado Rockies",
    "CWS": "Chicago White Sox", "CHW": "Chicago White Sox",
    "DET": "Detroit Tigers", "HOU": "Houston Astros", "KAN": "Kansas City Royals",
    "KC": "Kansas City Royals", "LAA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers", "LOS": "Los Angeles Dodgers",
    "MIA": "Miami Marlins", "MIL": "Milwaukee Brewers", "MIN": "Minnesota Twins",
    "NYM": "New York Mets", "NYY": "New York Yankees", "OAK": "Athletics",
    "PHI": "Philadelphia Phillies", "PIT": "Pittsburgh Pirates", "SDG": "San Diego Padres",
    "SD": "San Diego Padres", "SEA": "Seattle Mariners",
    "SFG": "San Francisco Giants", "SFO": "San Francisco Giants", "SF": "San Francisco Giants",
    "STL": "St. Louis Cardinals", "TAM": "Tampa Bay Rays", "TB": "Tampa Bay Rays",
    "TEX": "Texas Rangers", "TOR": "Toronto Blue Jays", "WAS": "Washington Nationals",
    "WSH": "Washington Nationals",
}

# Normalize a full team name to a stable key (handles franchise renames)
_ALIAS = {
    "cleveland indians": "cleveland guardians",
    "oakland athletics": "athletics",
    "sacramento athletics": "athletics",
}

def norm_team(name):
    n = " ".join(str(name).lower().split())
    return _ALIAS.get(n, n)

def _key(code_or_name):
    full = _SBR.get(str(code_or_name).strip().upper())
    return norm_team(full) if full else norm_team(code_or_name)

def _ml(v):
    """Parse a moneyline cell. SBR uses 'NL'/'' for missing, and '100' style ints."""
    try:
        s = str(v).strip().upper()
        if s in ("", "NL", "NAN", "PK"):
            return None
        f = float(s)
        # SBR sometimes stores +100 favorites as 100; leave as-is (American odds)
        return int(round(f))
    except (TypeError, ValueError):
        return None

def _find_file(season):
    for pat in (f"mlb-odds-{season}.xls*", f"mlb odds {season}.xls*",
                f"*odds*{season}*.xls*", f"*{season}*odds*.xls*"):
        hits = sorted(P.glob(pat))
        if hits:
            return hits[-1]
    return None

def closing_odds(season):
    if season in _CACHE:
        return _CACHE[season]
    out = {}
    f = _find_file(season)
    if not f:
        _CACHE[season] = out
        return out
    try:
        df = pd.read_excel(f)
    except Exception as e:
        print(f"  [Odds] could not read {f.name}: {e}")
        _CACHE[season] = out
        return out
    df = df.reset_index(drop=True)
    rows = df.to_dict("records")
    i = 0
    while i < len(rows) - 1:
        v, h = rows[i], rows[i + 1]
        if str(v.get("VH")).strip().upper() != "V" or str(h.get("VH")).strip().upper() != "H":
            i += 1
            continue
        try:
            d = int(v["Date"])
            mm, dd = d // 100, d % 100
            date_iso = f"{int(season):04d}-{mm:02d}-{dd:02d}"
        except Exception:
            i += 2
            continue
        away, home = _key(v.get("Team")), _key(h.get("Team"))
        out[(date_iso, away, home)] = {
            "date": date_iso,
            "away_team": _SBR.get(str(v.get("Team")).strip().upper(), str(v.get("Team"))),
            "home_team": _SBR.get(str(h.get("Team")).strip().upper(), str(h.get("Team"))),
            "away_open":  _ml(v.get("Open")),  "home_open":  _ml(h.get("Open")),
            "away_close": _ml(v.get("Close")), "home_close": _ml(h.get("Close")),
        }
        i += 2
    _CACHE[season] = out
    print(f"  [Odds] {f.name}: {len(out)} games with closing lines.")
    return out

def lookup(date_iso, away_name, home_name):
    season = int(str(date_iso)[:4])
    return closing_odds(season).get((date_iso, norm_team(away_name), norm_team(home_name)))

def seasons_available():
    return [y for y in range(2015, 2027) if _find_file(y)]


if __name__ == "__main__":
    print("seasons found:", seasons_available())
    od = closing_odds(2021)
    for k, v in list(od.items())[:3]:
        print(k, "->", v["away_team"], v["away_close"], "/", v["home_team"], v["home_close"])
