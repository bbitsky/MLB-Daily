"""mlb_intel.py — real betting & social trend generators for the dashboard.

Produces the BETTOR_NEWS and SOCIAL_INTEL lists that build_*.py used to
hardcode, from live data:

  * weather_intel()        — Open-Meteo (free, no key), dome-aware
  * bettor_news_from_odds()— multi-book line shopping + book disagreement
  * snapshot_odds()/line_movement_intel() — odds snapshots -> steam / RLM
  * injury_intel()         — MLB Stats API roster injury report (best-effort)
  * build_social_intel()/build_bettor_news() — convenience aggregators

Design rule: EVERY function degrades gracefully. On any network or parse
error it returns [] or None so the dashboard always renders. All three live
data sources (Open-Meteo, The Odds API, MLB Stats API) are simply unavailable
in the sandbox; on Windows they resolve normally.
"""
from __future__ import annotations
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

try:
    import requests
except Exception:                       # pragma: no cover
    requests = None

try:
    from mlb_data import DB_PATH, DOME_PARKS, _MLB_TEAM_IDS, _mlb_get
except Exception:                       # pragma: no cover
    DB_PATH, DOME_PARKS, _MLB_TEAM_IDS = None, {}, {}
    def _mlb_get(*a, **k): return {}

# ── Ballpark coordinates (lat, lon) for weather ───────────────────────────────
BALLPARK_COORDS = {
    "Angel Stadium":                   (33.8003, -117.8827),
    "Busch Stadium":                   (38.6226,  -90.1928),
    "Chase Field":                     (33.4455, -112.0667),
    "Citi Field":                      (40.7571,  -73.8458),
    "Citizens Bank Park":              (39.9061,  -75.1665),
    "Comerica Park":                   (42.3390,  -83.0485),
    "Coors Field":                     (39.7559, -104.9942),
    "Daikin Park":                     (29.7573,  -95.3555),
    "Dodger Stadium":                  (34.0739, -118.2400),
    "Fenway Park":                     (42.3467,  -71.0972),
    "Globe Life Field":                (32.7473,  -97.0847),
    "Great American Ball Park":        (39.0975,  -84.5069),
    "Guaranteed Rate Field":           (41.8299,  -87.6338),
    "Rate Field":                      (41.8299,  -87.6338),
    "Kauffman Stadium":                (39.0517,  -94.4803),
    "loanDepot park":                  (25.7781,  -80.2196),
    "American Family Field":           (43.0280,  -87.9712),
    "Nationals Park":                  (38.8730,  -77.0074),
    "Oracle Park":                     (37.7786, -122.3893),
    "Oriole Park at Camden Yards":     (39.2840,  -76.6217),
    "PNC Park":                        (40.4469,  -80.0057),
    "Petco Park":                      (32.7073, -117.1566),
    "Progressive Field":               (41.4962,  -81.6852),
    "Rogers Centre":                   (43.6414,  -79.3894),
    "Sutter Health Park":              (38.5804, -121.5133),
    "T-Mobile Park":                   (47.5914, -122.3325),
    "Target Field":                    (44.9817,  -93.2776),
    "Truist Park":                     (33.8907,  -84.4677),
    "Wrigley Field":                   (41.9484,  -87.6553),
    "Yankee Stadium":                  (40.8296,  -73.9262),
}

# Retractable-roof / dome parks (roof state unknown from the forecast, so we
# label them controlled/neutral). Merged with mlb_data.DOME_PARKS at runtime.
_RETRACTABLE = {
    "Chase Field", "Daikin Park", "Globe Life Field", "loanDepot park",
    "American Family Field", "Rogers Centre", "T-Mobile Park",
}

_WIND_DIRS = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
              "S","SSW","SW","WSW","W","WNW","NW","NNW"]

def _deg_to_compass(deg):
    try:
        return _WIND_DIRS[int((float(deg) / 22.5) + 0.5) % 16]
    except Exception:
        return "?"

def _is_covered(venue):
    return venue in _RETRACTABLE or venue in (DOME_PARKS or {})

# ── Odds helpers (The Odds API event shape) ───────────────────────────────────
def _implied(ml):
    ml = float(ml)
    return 100.0 / (ml + 100.0) if ml > 0 else abs(ml) / (abs(ml) + 100.0)

def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0

def _median_ml(mls):
    """Median by implied prob, returned as an American ML int."""
    mls = [m for m in mls if m is not None]
    if not mls:
        return None
    p = _median([_implied(m) for m in mls])
    p = max(0.01, min(0.99, p))
    return -round(p / (1 - p) * 100) if p >= 0.5 else round((1 - p) / p * 100)

def _book_h2h(event):
    """Return (away, home, [(book, away_ml, home_ml), ...]) for an Odds API event."""
    away, home = event.get("away_team"), event.get("home_team")
    rows = []
    for b in event.get("bookmakers", []):
        for m in b.get("markets", []):
            if m.get("key") != "h2h":
                continue
            o = {x.get("name"): x.get("price") for x in m.get("outcomes", [])}
            if away in o and home in o:
                rows.append((b.get("title") or b.get("key"), o[away], o[home]))
    return away, home, rows

def _fmt_ml(ml):
    if ml is None:
        return "n/a"
    return f"+{ml}" if ml > 0 else str(ml)

# ── 1. WEATHER (Open-Meteo) ───────────────────────────────────────────────────
def fetch_weather(venue, first_pitch_iso=None):
    """Return a weather dict for a venue, or None. Dome/retractable -> neutral."""
    if _is_covered(venue):
        return {"venue": venue, "dome": True,
                "summary": "Dome / retractable roof — controlled, wind-free conditions"}
    coords = BALLPARK_COORDS.get(venue)
    if not coords or requests is None:
        return None
    lat, lon = coords
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "hourly": "temperature_2m,wind_speed_10m,wind_direction_10m,precipitation_probability",
            "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
            "forecast_days": 2, "timezone": "auto"}, timeout=15)
        r.raise_for_status()
        h = r.json().get("hourly", {})
        times = h.get("time", [])
        if not times:
            return None
        idx = _nearest_hour_idx(times, first_pitch_iso)
        temp = round(h["temperature_2m"][idx])
        wind = round(h["wind_speed_10m"][idx])
        wdir = h["wind_direction_10m"][idx]
        pop  = h["precipitation_probability"][idx]
        comp = _deg_to_compass(wdir)
        return {"venue": venue, "dome": False, "temp_f": temp, "wind_mph": wind,
                "wind_dir": comp, "precip_pct": pop,
                "summary": f"{temp}°F, wind {wind} mph {comp}, {pop}% precip"}
    except Exception:
        return None

def _nearest_hour_idx(times, target_iso):
    """Index into the hourly `time` list closest to first pitch (default 7pm local)."""
    tt = None
    if target_iso:
        try:
            tt = datetime.fromisoformat(str(target_iso).replace("Z", ""))
        except Exception:
            tt = None
    if tt is None:
        for i, t in enumerate(times):
            if t.endswith("T19:00"):
                return i
        return min(len(times) - 1, 18)
    best, bestd = 0, float("inf")
    for i, t in enumerate(times):
        try:
            dt = datetime.fromisoformat(t)
        except Exception:
            continue
        d = abs((dt - tt.replace(tzinfo=None)).total_seconds())
        if d < bestd:
            best, bestd = i, d
    return best

def weather_intel(games):
    """Build SOCIAL_INTEL weather items from a list of game dicts (venue, teams)."""
    out = []
    for g in games:
        venue = g.get("venue") or ""
        away, home = g.get("away_team", ""), g.get("home_team", "")
        w = fetch_weather(venue, g.get("first_pitch") or g.get("commence_time"))
        if not w:
            continue
        if w.get("dome"):
            desc = w["summary"] + "."
        else:
            note = ""
            if w["wind_mph"] >= 12:
                note = f" Wind {w['wind_mph']} mph {w['wind_dir']} is a real factor for the total."
            if w["precip_pct"] >= 50:
                note += f" Rain risk {w['precip_pct']}% — watch for delay/postponement."
            elif w["temp_f"] >= 88:
                note += " Heat aids ball flight (favors hitters)."
            elif w["temp_f"] <= 50:
                note += " Cool air suppresses ball flight (favors pitchers)."
            desc = f"{w['summary']}.{note}"
        out.append({"type": "WEATHER", "topic": f"{venue} ({away} @ {home})", "desc": desc})
    return out

# ── 2. BETTING TRENDS from multi-book odds ────────────────────────────────────
def bettor_news_from_odds(events, min_edge_cents=8, min_disagree=0.03, max_items=10):
    """Line-shopping value + book disagreement flags from Odds API events."""
    out = []
    for ev in events or []:
        away, home, rows = _book_h2h(ev)
        if len(rows) < 2:
            continue
        cons_away = _median_ml([r[1] for r in rows])
        cons_home = _median_ml([r[2] for r in rows])
        # Line shopping — best (most favorable) price for each side vs consensus.
        for side, idx, cons in (("away", 1, cons_away), ("home", 2, cons_home)):
            best = max(rows, key=lambda r: r[idx])  # highest ML number = best price for the bettor
            best_book, best_ml = best[0], best[idx]
            if cons is None or best_ml is None:
                continue
            gap = abs(best_ml - cons)
            team = away if side == "away" else home
            if gap >= min_edge_cents and best_ml > cons:
                out.append({"tag": "SHOP",
                    "headline": f"{team} — best price {_fmt_ml(best_ml)} at {best_book} (consensus {_fmt_ml(cons)})",
                    "meta": f"Line-shopping value: {best_book} is {gap} cents better than the market median across {len(rows)} books. Take the number before it moves."})
        # Book disagreement — spread of implied prob across books on the home side.
        implied = [_implied(r[2]) for r in rows]
        spread = max(implied) - min(implied)
        if spread >= min_disagree:
            out.append({"tag": "SPLIT",
                "headline": f"{away} @ {home} — books disagree ({spread*100:.1f}% implied spread)",
                "meta": f"Home ML ranges {_fmt_ml(min(rows,key=lambda r:r[2])[2])} to {_fmt_ml(max(rows,key=lambda r:r[2])[2])} across {len(rows)} books — an unsettled market worth monitoring for value."})
    return out[:max_items]

# ── 3. LINE MOVEMENT (odds snapshots) ─────────────────────────────────────────
_SNAP_DDL = """
CREATE TABLE IF NOT EXISTS odds_snapshots (
    ts        TEXT,
    game_date TEXT,
    away_team TEXT,
    home_team TEXT,
    away_ml   INTEGER,
    home_ml   INTEGER,
    book      TEXT,
    PRIMARY KEY (ts, game_date, away_team, home_team, book)
)"""

def _conn(db=None):
    return sqlite3.connect(str(db or DB_PATH), timeout=30)

def snapshot_odds(target_date, events, db=None):
    """Store this fetch's consensus lines so movement can be measured later."""
    con = _conn(db); con.execute(_SNAP_DDL)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = 0
    for ev in events or []:
        away, home, rows = _book_h2h(ev)
        if not rows:
            continue
        aml = _median_ml([r[1] for r in rows])
        hml = _median_ml([r[2] for r in rows])
        con.execute("INSERT OR REPLACE INTO odds_snapshots VALUES (?,?,?,?,?,?,?)",
                    (ts, target_date, away, home, aml, hml, "CONSENSUS"))
        n += 1
    con.commit(); con.close()
    return ts, n

def line_movement_intel(target_date, db=None, min_move=0.02):
    """Compare first vs latest consensus snapshot for each game -> movement items."""
    try:
        con = _conn(db); con.execute(_SNAP_DDL)
        rows = con.execute(
            "SELECT away_team, home_team, ts, away_ml, home_ml FROM odds_snapshots "
            "WHERE game_date=? AND book='CONSENSUS' ORDER BY ts", (target_date,)).fetchall()
        con.close()
    except Exception:
        return []
    grouped = defaultdict(list)
    for a, h, ts, aml, hml in rows:
        grouped[(a, h)].append((ts, aml, hml))
    out = []
    for (a, h), snaps in grouped.items():
        if len(snaps) < 2:
            continue
        _, _, h0 = snaps[0]
        _, _, h1 = snaps[-1]
        if h0 is None or h1 is None:
            continue
        move = _implied(h1) - _implied(h0)          # + = money toward home
        if abs(move) < min_move:
            continue
        toward = h if move > 0 else a
        tag = "STEAM" if abs(move) >= 0.04 else "MOVE"
        out.append({"tag": tag,
            "headline": f"{a} @ {h} — line moved toward {toward} ({move*100:+.1f}% implied)",
            "meta": f"Home consensus ML {_fmt_ml(h0)} → {_fmt_ml(h1)} since first snapshot today "
                    f"({len(snaps)} snapshots). {'Sharp steam' if tag=='STEAM' else 'Gradual drift'} toward {toward}."})
    return out

# ── 4. INJURIES / LINEUPS (MLB Stats API, best-effort) ────────────────────────
def fetch_team_injuries(team_name):
    """Return [{'name','status','detail'}] of injured players, or []. Best-effort."""
    tid = (_MLB_TEAM_IDS or {}).get(team_name)
    if not tid:
        return []
    try:
        data = _mlb_get(f"teams/{tid}/roster",
                        {"rosterType": "fullRoster", "hydrate": "person(injury)"})
        out = []
        for entry in (data or {}).get("roster", []):
            status = (entry.get("status") or {}).get("description", "")
            if status and status.lower() not in ("active", ""):
                person = entry.get("person", {})
                inj = person.get("injury") or {}
                detail = inj.get("description") or status
                out.append({"name": person.get("fullName", "?"),
                            "status": status, "detail": detail})
        return out
    except Exception:
        return []

def injury_intel(games, max_per_game=3):
    """Build SOCIAL_INTEL injury items for the teams on the slate."""
    out = []
    seen = set()
    for g in games:
        for team in (g.get("away_team"), g.get("home_team")):
            if not team or team in seen:
                continue
            seen.add(team)
            inj = fetch_team_injuries(team)
            if not inj:
                continue
            names = ", ".join(f"{i['name']} ({i['detail']})" for i in inj[:max_per_game])
            more = f" +{len(inj)-max_per_game} more" if len(inj) > max_per_game else ""
            out.append({"type": "INJURY", "topic": f"{team} — {len(inj)} on injury report",
                        "desc": f"{names}{more}."})
    return out

# ── Convenience aggregators ───────────────────────────────────────────────────
def build_bettor_news(events, target_date=None, db=None, do_snapshot=True):
    """Full betting-trends list: line movement (if history) + shopping/disagreement."""
    news = []
    if events and target_date and do_snapshot:
        try:
            snapshot_odds(target_date, events, db=db)
        except Exception:
            pass
    if target_date:
        news += line_movement_intel(target_date, db=db)
    news += bettor_news_from_odds(events)
    return news

def build_social_intel(games, want_injuries=True):
    """Full social-intel list: weather (+ injuries if MLB API reachable)."""
    intel = weather_intel(games)
    if want_injuries:
        intel += injury_intel(games)
    return intel


# ── Light schedule fetch + one-call intel generator ───────────────────────────
def fetch_today_games_light(target_date=None):
    """Lightweight schedule pull for intel: [{venue, away_team, home_team,
    first_pitch}]. Just teams+venue+time — none of the heavy stat pulls that
    fetch_today_game_data does. Returns [] on any failure."""
    if requests is None:
        return []
    try:
        import datetime as _dt
        target_date = target_date or _dt.datetime.now().strftime("%Y-%m-%d")
        data = _mlb_get("schedule", {"sportId": 1, "date": target_date,
                                     "gameType": "R", "hydrate": "venue"})
        out = []
        for d in (data or {}).get("dates", []):
            for g in d.get("games", []):
                teams = g.get("teams", {})
                out.append({
                    "away_team": teams.get("away", {}).get("team", {}).get("name", ""),
                    "home_team": teams.get("home", {}).get("team", {}).get("name", ""),
                    "venue":     g.get("venue", {}).get("name", ""),
                    "first_pitch": g.get("gameDate", ""),
                })
        return out
    except Exception:
        return []


def generate_intel(target_date, events=None, db=None, games=None):
    """One call -> (bettor_news, social_intel) from live sources.

    Fetches today's odds (for line shopping / movement, snapshotting as it goes)
    and today's games (for weather / injuries). Everything degrades to empty on
    failure, so callers can pass the results straight to generate_html().
    """
    if events is None:
        try:
            from mlb_data import fetch_today_odds
            events = fetch_today_odds(target_date=target_date)
        except Exception:
            events = []
    if games is None:
        games = fetch_today_games_light(target_date)
    bettor = build_bettor_news(events, target_date, db=db)
    social = build_social_intel(games)
    return bettor, social
