"""mlb_edge.py -- single source of truth for probability adjustments, conviction
sizing, and dual-book pick logging.

Imported by mlb_daily.py (automated path) and the build_julyN.py nightly-fallback
template so both stay in sync instead of each redefining the logic.

CALIBRATION NOTE (week 1: 2026-06-26..07-04, 30 graded bets):
  * Underdogs went 13-4 (+46% ROI); favorites 5-8 (-27% ROI).
  * The biggest-size tiers were net losers -- HIGH 4-4 (-4.5% ROI),
    MED-HIGH 1-2 (-52%) -- while MEDIUM 9-3 (+57%) carried the card. The two
    worst bets were heavy-chalk HIGH favorites (MIL -169, ATL -162, both losses).
  => (a) soft-cap and de-size FAVORITES, (b) cap top size (no 1.0u) until the
     model proves out, (c) feed the formula BETTER ERA inputs (recent-form +
     FIP/xERA regression + park-variance discount) so edges are more reliable.
  These constants are calibrated on a TINY sample -- re-derive as N grows; do not
  treat them as precise. Everything here is deliberately mild to avoid overfitting.
"""

LEAGUE_AVG_ERA = 4.20

# ---------------------------------------------------------------- ERA inputs
def blended_era(era, last5_era=None, fip=None, xera=None):
    """The ERA the formula SHOULD use, not the raw season number.

    - Regress toward FIP/xERA: season ERA over/under-performs its peripherals
      (e.g. E-Rod 2.21 ERA / 3.98 FIP -> regressed upward).
    - Weight recent form: blend in last-5-starts ERA so collapses/hot streaks
      surface automatically (e.g. McLean 4.01 season / 6.92 last-month -> up).
    Weights are intentionally mild given small samples.
    """
    if era is None:
        era = LEAGUE_AVG_ERA
    base = float(era)
    periph = xera if xera is not None else fip          # prefer xERA, else FIP
    if periph is not None:
        base = 0.65 * base + 0.35 * float(periph)
    if last5_era is not None:
        base = 0.75 * base + 0.25 * float(last5_era)
    return base

# ---------------------------------------------------------------- park variance
def park_discount(park_factor):
    """Edge multiplier for high-variance parks. Encodes the July-2 Coors lesson:
    a starter ERA edge is far less reliable at altitude. Coors (~1.35) halves the
    edge; normal parks unchanged."""
    pf = float(park_factor or 1.0)
    if pf >= 1.30: return 0.50
    if pf >= 1.20: return 0.65
    if pf >= 1.12: return 0.80
    return 1.0

# ---------------------------------------------------------------- base formula
def formula_prob(away_era, home_era, away_wp=0.500, home_wp=0.500):
    """ERA-differential + win% fallback (unchanged core). Returns AWAY win prob."""
    era_diff = home_era - away_era
    wp_diff  = away_wp - home_wp
    return max(0.32, min(0.68, 0.47 + era_diff * 0.028 + wp_diff * 0.15))

def adjusted_edge(raw_edge, park_factor=1.0):
    """Shrink a raw model edge for park variance before sizing."""
    return raw_edge * park_discount(park_factor)

# ---------------------------------------------------------------- sanity gate
def implied(ml):
    """Vig-inclusive implied win prob from an American moneyline."""
    if ml is None:
        return 0.5
    return (100.0 / (ml + 100.0)) if ml > 0 else (abs(ml) / (abs(ml) + 100.0))

def market_novig_away(away_ml, home_ml):
    """No-vig market win prob for the AWAY side (removes the hold)."""
    ia, ih = implied(away_ml), implied(home_ml)
    return 0.5 if (ia + ih) == 0 else ia / (ia + ih)

def prob_is_sane(away_prob, away_ml, home_ml, max_gap=0.15, flip_gap=0.08,
                 clear_fav=0.55):
    """Guardrail vs corrupted/inverted model probabilities.

    Added 2026-07-12 after the numberFire feed came through INVERTED (favorites
    listed under 50%, plus-money dogs over 50%), which manufactured phantom edges
    and drove an 0-4 day. An efficient MLB moneyline rarely misprices a side by
    more than ~10-12 pts, so we treat a big model-vs-market disagreement as bad
    data, not alpha.

    Returns (ok, gap). NOT ok (=> void the bet) when the model:
      * flips which side is favored AND disagrees with the no-vig market by
        more than `flip_gap`, or
      * disagrees with the market by more than `max_gap` on either side, or
      * models a CLEAR market favorite (no-vig >= `clear_fav`) as an outright
        underdog (<50%) — the exact signature of an inverted feed.
    A legit small edge (model likes a dog a bit more than the market, same side)
    is NOT flagged.
    """
    if away_prob is None or away_ml is None or home_ml is None:
        return True, 0.0
    mkt = market_novig_away(away_ml, home_ml)
    gap = abs(away_prob - mkt)
    flips = (away_prob > 0.5) != (mkt > 0.5)
    clear_flip = (mkt >= clear_fav and away_prob < 0.50) or \
                 (mkt <= 1 - clear_fav and away_prob > 0.50)
    ok = not ((flips and gap > flip_gap) or gap > max_gap or clear_flip)
    return ok, gap

def gate_game(game):
    """Apply prob_is_sane to a built game dict IN PLACE. If insane, zero both
    sides' edges (so conviction() yields NO PLAY) and append an explanatory flag.
    Safe to call on any game dict that has away_prob/away_ml/home_ml. Returns the
    game. Both the automated (mlb_daily) and nightly (build_julyN) paths call this
    so a corrupted feed can never mint a pick again."""
    ap = game.get("away_prob"); aml = game.get("away_ml"); hml = game.get("home_ml")
    ok, gap = prob_is_sane(ap, aml, hml)
    if not ok:
        game["away_edge"] = 0.0
        game["home_edge"] = 0.0
        game["away_units"] = 0.0
        game["home_units"] = 0.0
        game["away_conv"] = "NO PLAY"
        game["home_conv"] = "NO PLAY"
        mkt = market_novig_away(aml, hml)
        game.setdefault("flags", []).append(
            f"nF-sanity: model {ap:.0%} vs market {mkt:.0%} (gap {gap:.0%}) "
            f"— implausible, likely bad numberFire; bet voided")
    return game

def flagged_games(games):
    """Matchup strings for every game the sanity gate voided (nF-sanity flag)."""
    out = []
    for g in games or []:
        for f in (g.get("flags") or []):
            if isinstance(f, str) and f.startswith("nF-sanity"):
                out.append(f"{g.get('away_team','?')} @ {g.get('home_team','?')}")
                break
    return out

def health_banner_html(games):
    """Red/amber dashboard banner when the guardrail voided games (a corrupt
    numberFire feed). Returns '' when nothing is flagged. 3+ flagged = treat the
    whole slate as suspect."""
    flagged = flagged_games(games)
    n = len(flagged)
    if n == 0:
        return ""
    sev = "#ef5350" if n >= 3 else "#ffca28"
    head = (f"⚠ numberFire feed looks CORRUPT — {n} games auto-voided"
            if n >= 3 else f"⚠ {n} game(s) auto-voided by the sanity gate")
    extra = ("If this many are flagged the whole slate is suspect — re-pull "
             "numberFire before trusting any pick." if n >= 3 else "")
    lis = "".join(f"<li>{m}</li>" for m in flagged)
    return (f'<div style="background:#3a1216;border:1px solid {sev};border-radius:8px;'
            f'padding:14px 16px;margin:0 0 16px 0;color:#ffcdd2">'
            f'<div style="font-weight:700;color:{sev};font-size:15px;margin-bottom:6px">{head}</div>'
            f'The model probability implausibly contradicted the market on these games '
            f'(a clear favorite modelled as an underdog, or a &gt;15-point gap), so their bets '
            f'were voided as likely bad data. {extra}'
            f'<ul style="margin:8px 0 0 18px">{lis}</ul></div>')

def inject_health_banner(html, games):
    """Insert health_banner_html into a generated dashboard right after the picks
    panel opens. No-op if nothing flagged or the anchor isn't found."""
    banner = health_banner_html(games)
    if not banner:
        return html
    import re
    m = re.search(r'(id="tab-picks"[^>]*>)', html)
    return (html[:m.end()] + banner + html[m.end():]) if m else (banner + html)

# ---------------------------------------------------------------- conviction
def conviction(edge, ml):
    """(label, units) from edge, week-1 recalibrated.

    Favorites (ml<0): soft-capped -- no HIGH-size favorites, and a bigger edge is
    required to bet one at all (they went 5-8 / -27% ROI in week 1).
    Underdogs (ml>=0): the model's proven side (+46% ROI) -- keep the ladder but
    cap the top at 0.75u (down from 1.00u) on this small sample.
    """
    is_fav = ml is not None and ml < 0
    if is_fav:
        if edge >= 0.08: return "MEDIUM", 0.50      # capped: no HIGH favorites
        if edge >= 0.06: return "LEAN",   0.25
        return "NO PLAY", 0.0
    if edge >= 0.08:  return "HIGH",     0.75       # capped from 1.00
    if edge >= 0.06:  return "MED-HIGH", 0.60
    if edge >= 0.045: return "MEDIUM",   0.50
    if edge >= 0.02:  return "LEAN",     0.25
    return "NO PLAY", 0.0

# ---------------------------------------------------------------- dual-book log
def log_picks(db_path, game_date, candidates, replace_date=True):
    """Persist the full MODEL BOOK for a date so it can be graded honestly.

    Each candidate is a dict: pick_team, ml, my_prob, implied_prob, edge,
    conviction, units, and optional bet (1=actually staked, else 0).

    Every actionable candidate (units>0) is written with result=NULL so the next
    day's auto_log_results grades it -- giving us the MODEL's record
    (get_pick_record(bets_only=False)) alongside the DISCRETIONARY record
    (bets_only=True). Idempotent per (game_date, pick_team).
    Returns number of rows inserted. Never raises (logging must not break a run).
    """
    import sqlite3
    inserted = 0
    try:
        con = sqlite3.connect(str(db_path))
        cols = [r[1] for r in con.execute("PRAGMA table_info(picks)")]
        has_bet = "bet" in cols
        cur = con.cursor()
        for c in candidates:
            if c.get("units", 0) <= 0 and not c.get("bet"):
                continue  # only log the model's actionable book (+ anything staked)
            exists = cur.execute(
                "SELECT 1 FROM picks WHERE game_date=? AND pick_team=?",
                (game_date, c["pick_team"])).fetchone()
            if exists:
                continue
            fields = ["game_date","pick_team","ml","my_prob","implied_prob",
                      "edge","conviction","units","result","profit_loss"]
            vals   = [game_date, c["pick_team"], c.get("ml"), c.get("my_prob"),
                      c.get("implied_prob"), c.get("edge"), c.get("conviction"),
                      c.get("units"), None, None]
            if has_bet:
                fields.append("bet"); vals.append(1 if c.get("bet") else 0)
            ph = ",".join("?" * len(fields))
            cur.execute(f"INSERT INTO picks({','.join(fields)}) VALUES({ph})", vals)
            inserted += 1
        con.commit()
        try:
            con.execute("PRAGMA journal_mode=DELETE"); con.commit()
        except Exception:
            pass
        con.close()
    except Exception as e:
        print(f"  [mlb_edge.log_picks] WARN: {e} (picks not logged)")
    return inserted
