#!/usr/bin/env python3
"""
MLB Betting Model v2.1
Implements the full 11-step workflow from mlb_model_v2_june28_2026.md

Usage:
    python mlb_model.py              # interactive mode — enter one game at a time
    python mlb_model.py --batch      # batch mode — enter multiple games, get full slate report
"""

import sys
import json
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────

@dataclass
class StarterData:
    name: str
    era: float
    last7_era: float
    qs_rate: float          # 0–1 (e.g. 0.65 = 65%)
    ats_record_w: int
    ats_record_l: int
    rest_days: int
    career_era_vs_opp: Optional[float]  # None = never faced or unknown
    career_ip_vs_opp: float             # 0 if never faced

@dataclass
class TeamData:
    name: str
    record_w: int
    record_l: int
    home_away: str          # "home" or "away"
    home_w: int
    home_l: int
    away_w: int
    away_l: int
    il_score: int           # 60-day=3, 15-day=2, 10-day=1, DTD=0.5
    bvp_score: int          # 0=neutral, 1=weak, 2=moderate, 3=strong (3+ hitters OPS≥1.000 with 9+PA)
    same_handed_top6: int   # count of top-6 hitters same hand as opposing starter
    is_national_tv_marquee: bool  # is THIS team the marquee team getting public money

@dataclass
class GameData:
    # Teams & starters
    away_team: TeamData
    home_team: TeamData
    away_starter: StarterData
    home_starter: StarterData

    # Odds
    away_ml: int    # e.g. +120 or -110
    home_ml: int

    # Over/Under
    ou_line: float
    ou_direction: str   # "over" or "under" or "skip"

    # Venue / weather
    park: str
    is_dome: bool
    temp_f: float
    wind_mph: float
    wind_direction: str     # "out", "in", "crosswind", "calm"
    rain_pct: float         # 0–100
    rain_flagged_any_source: bool
    is_turf: bool

    # Context
    ump_run_favor: float    # positive = hitter-friendly, negative = pitcher-friendly
    series_game_num: int    # 1, 2, 3, or 4
    is_national_tv: bool
    day_after_blowout_team: Optional[str]   # "away" or "home" or None (team that won big yesterday)

    # Travel fatigue
    away_tz_displacement: int   # time zones crossed by away team (negative OK)
    is_early_game: bool         # before 2pm local park time?


# ─────────────────────────────────────────────
# PARK FACTORS
# ─────────────────────────────────────────────

PARK_RUN_ADJUSTMENTS = {
    "coors":    +1.5,
    "petco":    -0.75,   # night / marine layer
    "oracle":   -0.5,    # wind in 15+ mph only (handled in weather step)
    "fenway":   +0.3,
    "great american": +0.4,
    "guaranteed rate": +0.3,
}

PARK_WINPROB_HOME_BONUS = {
    "coors": +0.04,
}


def moneyline_to_prob(ml: int) -> float:
    """Convert American moneyline to implied probability (0–1)."""
    if ml < 0:
        return (-ml) / (-ml + 100)
    else:
        return 100 / (ml + 100)


def prob_to_moneyline(prob: float) -> str:
    """Convert probability to American moneyline string."""
    if prob <= 0 or prob >= 1:
        return "N/A"
    if prob >= 0.5:
        ml = -round((prob / (1 - prob)) * 100)
        return str(ml)
    else:
        ml = round(((1 - prob) / prob) * 100)
        return f"+{ml}"


def era_to_quality(era: float) -> str:
    if era <= 2.50: return "ELITE"
    if era <= 3.20: return "EXCELLENT"
    if era <= 3.80: return "GOOD"
    if era <= 4.50: return "AVERAGE"
    if era <= 5.50: return "BELOW AVG"
    return "POOR"


# ─────────────────────────────────────────────
# STEP-BY-STEP MODEL
# ─────────────────────────────────────────────

def run_model(g: GameData) -> dict:
    log = []        # audit trail of adjustments
    warnings = []   # flags / watch items

    # ── Step 1 baseline: team win probability from record + home advantage ──
    # Simple pythagorean-style win% from record
    away_wp = g.away_team.record_w / max(g.away_team.record_w + g.away_team.record_l, 1)
    home_wp = g.home_team.record_w / max(g.home_team.record_w + g.home_team.record_l, 1)

    # Blend record-based WP — home team gets ~4% structural home advantage
    total = away_wp + home_wp
    away_base = (away_wp / total) * 0.50 - 0.02  # home advantage taken from away
    home_base = (home_wp / total) * 0.50 + 0.02

    log.append(f"[Base] Record-based WP → Away {away_base:.1%} | Home {home_base:.1%}")

    # ── Step 1b: Umpire adjustment ──
    ou_adj = 0.0
    if g.ump_run_favor > 0.3:
        away_base += 0.01
        home_base += 0.01
        ou_adj += 0.3
        log.append(f"[Ump] Hitter-friendly (run favor +{g.ump_run_favor:.1f}) → +0.3 O/U")
    elif g.ump_run_favor < -0.3:
        ou_adj -= 0.3
        log.append(f"[Ump] Pitcher-friendly (run favor {g.ump_run_favor:.1f}) → -0.3 O/U")
        # slight away pitcher boost (away_starter pitching against home batters)
        # handled as neutral — both pitchers benefit equally

    # ── Step 1c: Series context ──
    if g.series_game_num >= 3:
        ou_adj += 0.2
        log.append(f"[Series] Game {g.series_game_num} → bullpen fatigue lean +0.2 O/U")
    elif g.series_game_num == 1:
        ou_adj -= 0.2
        log.append(f"[Series] Game 1 → rested bullpens -0.2 O/U")

    # ── Step 1d: Pitcher rest days ──
    for side, starter in [("Away", g.away_starter), ("Home", g.home_starter)]:
        if starter.rest_days <= 3:
            if side == "Away":
                away_base -= 0.03
            else:
                home_base -= 0.03
            ou_adj += 0.3
            warnings.append(f"⚠️  {side} starter {starter.name}: SHORT REST ({starter.rest_days}d) → -3% WP, +0.3 O/U")
        elif starter.rest_days >= 7:
            warnings.append(f"⚠️  {side} starter {starter.name}: EXTENDED REST ({starter.rest_days}d) — rust flag, monitor")

    # ── Step 2: BvP integration ──
    # Team BvP score: 0=neutral, 1=+3%, 2=+5%, 3=+7%
    BVP_BOOSTS = {0: 0.0, 1: 0.02, 2: 0.03, 3: 0.06}

    away_bvp_boost = BVP_BOOSTS.get(g.away_team.bvp_score, 0.0)
    home_bvp_boost = BVP_BOOSTS.get(g.home_team.bvp_score, 0.0)

    away_base += away_bvp_boost
    home_base += home_bvp_boost

    if away_bvp_boost > 0:
        log.append(f"[BvP] Away offense BvP score {g.away_team.bvp_score} → +{away_bvp_boost:.0%} WP")
    if home_bvp_boost > 0:
        log.append(f"[BvP] Home offense BvP score {g.home_team.bvp_score} → +{home_bvp_boost:.0%} WP")

    # Pitcher vs specific team ERA
    for side, starter, opp in [
        ("Away", g.away_starter, g.home_team),
        ("Home", g.home_starter, g.away_team)
    ]:
        if starter.career_ip_vs_opp >= 15 and starter.career_era_vs_opp is not None:
            era_gap = starter.career_era_vs_opp - starter.era
            if era_gap >= 1.5:
                # pitcher struggles vs this team — boost the batting team
                if side == "Away":
                    home_base += 0.04
                    away_base -= 0.04
                else:
                    away_base += 0.04
                    home_base -= 0.04
                log.append(f"[BvP-ERA] {starter.name} career ERA vs opp {starter.career_era_vs_opp:.2f} "
                           f"(+{era_gap:.2f} vs season ERA) → opponent +4%")
                warnings.append(f"⚠️  {starter.name} ERA vs {opp.name}: {starter.career_era_vs_opp:.2f} "
                                f"vs season {starter.era:.2f} — pitcher struggles here")
        elif starter.career_ip_vs_opp == 0:
            # Never faced — slight batting team boost
            if side == "Away":
                home_base += 0.02
            else:
                away_base += 0.02
            log.append(f"[BvP] {starter.name} never faced {opp.name} → opponent +2% (unknown = mean regression)")
        elif starter.career_ip_vs_opp < 15:
            warnings.append(f"⚠️  {starter.name} career IP vs {opp.name}: {starter.career_ip_vs_opp:.0f} IP "
                           f"— below 15-IP threshold, discount BvP signal")

    # ── Step 2b: Lineup handedness stack ──
    # away_team's same_handed_top6 = same-hand vs HOME starter
    for side, team, handicapped_dir in [
        ("Away", g.away_team, "away"),
        ("Home", g.home_team, "home")
    ]:
        sh = team.same_handed_top6
        if sh >= 5:
            adj = -0.04
        elif sh == 4:
            adj = -0.02
        else:
            adj = 0.0

        if adj != 0:
            if handicapped_dir == "away":
                away_base += adj
                home_base -= adj
            else:
                home_base += adj
                away_base -= adj
            log.append(f"[LH Stack] {side} has {sh} same-handed batters vs opposing starter → {adj:.0%} WP")

    # ── Step 3: Weather ──
    park_key = g.park.lower()

    if g.rain_pct > 60 or (g.rain_flagged_any_source and g.rain_pct > 30):
        warnings.append(f"🌧️  RAIN RISK: {g.rain_pct:.0f}% / flagged={g.rain_flagged_any_source} → SKIP or CONDITIONAL (half unit)")
    elif g.rain_flagged_any_source:
        warnings.append(f"🌧️  Rain flagged by one source despite low % → CONDITIONAL pick")

    if not g.is_dome:
        # Park run adjustment
        park_ou_adj = 0.0
        for k, v in PARK_RUN_ADJUSTMENTS.items():
            if k in park_key:
                # Oracle only if wind in
                if k == "oracle" and not (g.wind_direction == "in" and g.wind_mph >= 15):
                    continue
                park_ou_adj += v
                log.append(f"[Park] {g.park} adjustment → {v:+.2f} runs O/U")
                break

        # Heat + wind out bonus
        if g.temp_f > 80 and g.wind_direction == "out" and g.wind_mph > 10:
            park_ou_adj += 0.75
            log.append(f"[Weather] Heat {g.temp_f:.0f}°F + wind out {g.wind_mph:.0f}mph → +0.75 O/U")

        # Park home team WP bonus (Coors)
        for k, v in PARK_WINPROB_HOME_BONUS.items():
            if k in park_key:
                home_base += v
                log.append(f"[Park] {g.park} home altitude familiarity → +{v:.0%} home WP")
                break

        ou_adj += park_ou_adj

        # Surface: turf penalty for groundball pitchers
        if g.is_turf:
            for side, starter in [("Away", g.away_starter), ("Home", g.home_starter)]:
                log.append(f"[Surface] Turf park — verify {starter.name} GB% (if >55%, +0.2 eff ERA)")
            warnings.append("⚠️  Turf surface: GB% pitchers lose ~0.2 runs suppression — verify arsenals")

    # Travel fatigue
    if abs(g.away_tz_displacement) >= 2 and g.is_early_game:
        away_base -= 0.03
        log.append(f"[Travel] Away team crossed {abs(g.away_tz_displacement)} TZ for early game → -3% away WP")
        warnings.append(f"⚠️  Travel fatigue: {g.away_team.name} crossed {abs(g.away_tz_displacement)} TZ, early start")

    # ── Step 4: IL severity ──
    for side, team in [("Away", g.away_team), ("Home", g.home_team)]:
        il = team.il_score
        if il >= 15:
            if side == "Away":
                away_base -= 0.04
            else:
                home_base -= 0.04
            warnings.append(f"🚨 {side} IL score {il} ≥ 15: CAUTION — do not back favorites at -130 or shorter against {team.name}")
            log.append(f"[IL] {side} IL score {il} ≥ 15 → -4% WP + caution flag")
        elif il >= 10:
            if side == "Away":
                away_base -= 0.04
            else:
                home_base -= 0.04
            log.append(f"[IL] {side} IL score {il} ≥ 10 → -4% WP")

    # ── Step 5: Starter ERA differential ──
    # Blend in starter ERA quality vs league average (4.00 ERA = neutral)
    LEAGUE_AVG_ERA = 4.00

    def era_adj(era: float) -> float:
        """Returns WP boost: elite ERA = positive, poor ERA = negative. Max ±8%"""
        delta = LEAGUE_AVG_ERA - era  # positive = better than average
        return max(-0.08, min(0.08, delta * 0.025))

    away_era_adj = era_adj(g.away_starter.era)
    home_era_adj = era_adj(g.home_starter.era)

    away_base += away_era_adj
    home_base += home_era_adj

    log.append(f"[ERA] Away {g.away_starter.name} {g.away_starter.era:.2f} ERA → {away_era_adj:+.1%} WP")
    log.append(f"[ERA] Home {g.home_starter.name} {g.home_starter.era:.2f} ERA → {home_era_adj:+.1%} WP")

    # ATS record adjustment (starter-level signal)
    for side, starter in [("Away", g.away_starter), ("Home", g.home_starter)]:
        ats_total = starter.ats_record_w + starter.ats_record_l
        if ats_total >= 10:
            ats_rate = starter.ats_record_w / ats_total
            if ats_rate <= 0.35:
                # Ace discount: team underperforms spread in this pitcher's starts
                warnings.append(f"⚠️  ATS ACE DISCOUNT: {starter.name} ATS {starter.ats_record_w}-{starter.ats_record_l} "
                               f"({ats_rate:.0%}) — check if team is overpriced at -175+")
            elif ats_rate >= 0.65:
                warnings.append(f"✅ {starter.name} team ATS {starter.ats_record_w}-{starter.ats_record_l} "
                               f"({ats_rate:.0%}) — strong cover tendency")

    # ── Step 6: Last 7 GS form adjustment ──
    for side, starter in [("Away", g.away_starter), ("Home", g.home_starter)]:
        form_gap = starter.last7_era - starter.era
        if form_gap >= 2.0:
            # Struggling recently — discount BvP, flag form concern
            warnings.append(f"⚠️  {starter.name}: last-7 ERA {starter.last7_era:.2f} vs season {starter.era:.2f} "
                           f"(+{form_gap:.2f}) — poor recent form, discount historical BvP 20-30%")
            if side == "Away":
                away_base -= 0.02
            else:
                home_base -= 0.02
        elif form_gap <= -2.0:
            log.append(f"[Form] {starter.name} last-7 ERA {starter.last7_era:.2f} vs season {starter.era:.2f} "
                      f"({form_gap:.2f}) — hot streak, discount opponent BvP 30-40%")

    # ── Step 7: National TV / public money fade ──
    if g.is_national_tv:
        if g.away_team.is_national_tv_marquee:
            away_base -= 0.035
            home_base += 0.035
            log.append(f"[NatTV] {g.away_team.name} is marquee team on national TV → -3.5% away, +3.5% home (fade)")
        elif g.home_team.is_national_tv_marquee:
            home_base -= 0.035
            away_base += 0.035
            log.append(f"[NatTV] {g.home_team.name} is marquee team on national TV → -3.5% home, +3.5% away (fade)")
        warnings.append("📺 NATIONAL TV: Validated 3-for-3 fade on marquee team. Apply at full conviction.")

    # Day-after-blowout
    if g.day_after_blowout_team:
        opp = "home" if g.day_after_blowout_team == "away" else "away"
        boost = 0.03
        if opp == "away":
            away_base += boost
        else:
            home_base += boost
        log.append(f"[Blowout] {g.day_after_blowout_team.title()} team won big yesterday → opponent +3% (public money lean)")
        warnings.append("⚠️  Day-after-blowout: only 1 data point — use as lean, not primary driver")

    # ── Normalize to sum to 1.0 ──
    total_prob = away_base + home_base
    away_final = away_base / total_prob
    home_final = home_base / total_prob

    # ── Step 8: Edge calculation ──
    away_implied = moneyline_to_prob(g.away_ml)
    home_implied = moneyline_to_prob(g.home_ml)

    away_edge = away_final - away_implied
    home_edge = home_final - home_implied

    # ── Favorites tier check ──
    def favorites_tier_ok(ml: int, starter: StarterData, record_gap: int) -> tuple:
        """Returns (ok, reason)"""
        if ml >= -130:
            return True, "Standard conviction required (edge ≥ +5%)"
        elif ml >= -150:
            # Needs 1 of: ERA ≤ 3.20, QS ≥ 65%, record gap ≥ 18
            checks = []
            if starter.era <= 3.20: checks.append(f"ERA {starter.era:.2f} ≤ 3.20 ✅")
            if starter.qs_rate >= 0.65: checks.append(f"QS {starter.qs_rate:.0%} ≥ 65% ✅")
            if record_gap >= 18: checks.append(f"Record gap {record_gap} ≥ 18 ✅")
            if checks:
                return True, f"-130 to -150 tier: met 1+ criteria — {', '.join(checks)}"
            return False, f"-130 to -150 tier: NEEDS 1 of (ERA ≤ 3.20 / QS ≥ 65% / gap ≥ 18) — none met"
        else:  # -150+
            checks = []
            if starter.era <= 3.20: checks.append(f"ERA {starter.era:.2f} ≤ 3.20")
            if starter.qs_rate >= 0.65: checks.append(f"QS {starter.qs_rate:.0%} ≥ 65%")
            if record_gap >= 18: checks.append(f"Record gap {record_gap}")
            if len(checks) >= 2:
                return True, f"-150+ tier: met 2+ criteria — {', '.join(checks)}"
            if ml <= -162:
                return False, f"-162+ ML: evaluate RUN LINE or team total instead"
            return False, f"-150+ tier: NEEDS 2 of (ERA ≤ 3.20 / QS ≥ 65% / gap ≥ 18) — only {len(checks)} met"

    record_gap = abs(
        (g.away_team.record_w - g.away_team.record_l) -
        (g.home_team.record_w - g.home_team.record_l)
    )

    # ── Step 9: O/U adjusted total ──
    ou_note = ""
    if g.ou_direction != "skip":
        if g.ou_direction == "under":
            warnings.append("⚠️  UNDER rule: BOTH lineups must have suppression signals. "
                          "Elite offense (top-10 wRC+) requires ERA ≤ 3.00 + BvP confirmation on BOTH sides.")
        ou_note = f"O/U adjustment: {ou_adj:+.2f} runs vs line {g.ou_line}"

    # ── Conviction level ──
    def get_conviction(edge: float, ml: int, starter: StarterData, record_gap: int) -> tuple:
        tier_ok, tier_reason = favorites_tier_ok(ml, starter, record_gap)

        if not tier_ok:
            return "SKIP", 0.0, f"Favorites tier not met: {tier_reason}"

        if edge >= 0.08:
            return "HIGH", 1.0, f"Edge +{edge:.1%} ≥ 8% — HIGH conviction (1.0u)"
        elif edge >= 0.06:
            return "MEDIUM-HIGH", 0.75, f"Edge +{edge:.1%} — MEDIUM-HIGH (0.75u)"
        elif edge >= 0.05:
            return "MEDIUM", 0.5, f"Edge +{edge:.1%} — MEDIUM (0.5u)"
        elif edge >= 0.02:
            return "LEAN", 0.25, f"Edge +{edge:.1%} — LEAN (0.25u)"
        else:
            return "NO PLAY", 0.0, f"Edge +{edge:.1%} below 2% threshold"

    # Determine which side (if any) has value
    away_conviction, away_units, away_reason = get_conviction(
        away_edge, g.away_ml, g.away_starter, record_gap)
    home_conviction, home_units, home_reason = get_conviction(
        home_edge, g.home_ml, g.home_starter, record_gap)

    return {
        "away_team": g.away_team.name,
        "home_team": g.home_team.name,
        "away_starter": g.away_starter.name,
        "home_starter": g.home_starter.name,
        "away_win_prob": away_final,
        "home_win_prob": home_final,
        "away_ml": g.away_ml,
        "home_ml": g.home_ml,
        "away_implied": away_implied,
        "home_implied": home_implied,
        "away_edge": away_edge,
        "home_edge": home_edge,
        "away_conviction": away_conviction,
        "home_conviction": home_conviction,
        "away_units": away_units,
        "home_units": home_units,
        "away_reason": away_reason,
        "home_reason": home_reason,
        "ou_line": g.ou_line,
        "ou_direction": g.ou_direction,
        "ou_adj": ou_adj,
        "ou_note": ou_note,
        "log": log,
        "warnings": warnings,
        "record_gap": record_gap,
    }


# ─────────────────────────────────────────────
# OUTPUT FORMATTING
# ─────────────────────────────────────────────

def format_result(r: dict) -> str:
    lines = []
    sep = "─" * 60

    lines.append(sep)
    lines.append(f"  {r['away_team']} ({r['away_starter']})  @  {r['home_team']} ({r['home_starter']})")
    lines.append(sep)

    lines.append("\n📊 WIN PROBABILITIES")
    lines.append(f"  {r['away_team']:20s}  {r['away_win_prob']:.1%}  (market implied: {r['away_implied']:.1%})  Edge: {r['away_edge']:+.1%}")
    lines.append(f"  {r['home_team']:20s}  {r['home_win_prob']:.1%}  (market implied: {r['home_implied']:.1%})  Edge: {r['home_edge']:+.1%}")

    lines.append("\n💰 PICK RECOMMENDATION")

    # Best side
    picks = []
    if r['away_conviction'] not in ("NO PLAY", "SKIP"):
        picks.append((r['away_team'], r['away_ml'], r['away_conviction'], r['away_units'], r['away_reason'], r['away_edge']))
    if r['home_conviction'] not in ("NO PLAY", "SKIP"):
        picks.append((r['home_team'], r['home_ml'], r['home_conviction'], r['home_units'], r['home_reason'], r['home_edge']))

    # Sort by edge descending
    picks.sort(key=lambda x: x[5], reverse=True)

    if picks:
        for team, ml, conv, units, reason, edge in picks:
            ml_str = f"+{ml}" if ml > 0 else str(ml)
            lines.append(f"  ✅ {team} {ml_str} ML — {conv} ({units}u)")
            lines.append(f"     {reason}")
    else:
        # Check if tier blocked it
        skip_msgs = []
        if r['away_conviction'] == "SKIP":
            skip_msgs.append(f"  ⚠️  {r['away_team']}: {r['away_reason']}")
        if r['home_conviction'] == "SKIP":
            skip_msgs.append(f"  ⚠️  {r['home_team']}: {r['home_reason']}")
        if skip_msgs:
            lines.append("  ❌ NO PLAY (favorites tier not met)")
            lines.extend(skip_msgs)
        else:
            lines.append("  ❌ NO PLAY — insufficient edge on either side")

    # O/U
    if r['ou_direction'] != "skip":
        ou_adj_str = f"{r['ou_adj']:+.2f} runs vs line {r['ou_line']}"
        lines.append(f"\n📈 O/U: {r['ou_direction'].upper()} {r['ou_line']} | Run environment adjustment: {ou_adj_str}")
        adj_line = r['ou_line'] + (r['ou_adj'] if r['ou_direction'] == 'over' else -r['ou_adj'])
        lines.append(f"   Adjusted effective line: {adj_line:.1f}")
        if r['ou_note']:
            lines.append(f"   {r['ou_note']}")

    # Warnings
    if r['warnings']:
        lines.append("\n⚡ FLAGS & WARNINGS")
        for w in r['warnings']:
            lines.append(f"  {w}")

    # Adjustment log
    lines.append("\n📋 ADJUSTMENT LOG")
    for entry in r['log']:
        lines.append(f"  {entry}")

    lines.append(sep)
    return "\n".join(lines)


# ─────────────────────────────────────────────
# INPUT HELPERS
# ─────────────────────────────────────────────

def ask(prompt: str, default=None, cast=str):
    if default is not None:
        val = input(f"  {prompt} [{default}]: ").strip()
        if not val:
            return default
        return cast(val)
    else:
        while True:
            val = input(f"  {prompt}: ").strip()
            if val:
                return cast(val)
            print("  (required)")


def ask_float(prompt: str, default=None) -> float:
    return ask(prompt, default=default, cast=float)


def ask_int(prompt: str, default=None) -> int:
    return ask(prompt, default=default, cast=int)


def ask_bool(prompt: str, default=False) -> bool:
    default_str = "y" if default else "n"
    val = ask(f"{prompt} (y/n)", default=default_str).lower()
    return val.startswith("y")


def ask_ml(prompt: str) -> int:
    """Ask for a moneyline like +120 or -110."""
    while True:
        val = input(f"  {prompt} (e.g. +120 or -148): ").strip()
        if val:
            try:
                return int(val)
            except ValueError:
                print("  Enter a number like +120 or -148")


def input_starter(side: str) -> StarterData:
    print(f"\n  ── {side.upper()} STARTER ──")
    name = ask("Name")
    era = ask_float("Season ERA")
    last7 = ask_float("Last 7 GS ERA", default=era)
    qs = ask_float("QS rate (e.g. 0.65 for 65%)", default=0.50)
    ats_w = ask_int("ATS wins this season", default=0)
    ats_l = ask_int("ATS losses this season", default=0)
    rest = ask_int("Days rest (since last outing)", default=5)

    career_ip = ask_float("Career IP vs tonight's opp (0 = never faced)", default=0.0)
    career_era = None
    if career_ip > 0:
        career_era = ask_float(f"Career ERA vs tonight's opp ({career_ip:.0f} IP)")

    return StarterData(
        name=name,
        era=era,
        last7_era=last7,
        qs_rate=qs,
        ats_record_w=ats_w,
        ats_record_l=ats_l,
        rest_days=rest,
        career_era_vs_opp=career_era,
        career_ip_vs_opp=career_ip,
    )


def input_team(side: str, is_home: bool) -> TeamData:
    print(f"\n  ── {side.upper()} TEAM ──")
    name = ask("Team name")
    w = ask_int("Overall wins")
    l = ask_int("Overall losses")
    hw = ask_int("Home wins", default=0)
    hl = ask_int("Home losses", default=0)
    aw = ask_int("Away wins", default=0)
    al = ask_int("Away losses", default=0)
    il = ask_int("IL severity score (60d=3, 15d=2, 10d=1, DTD=1)", default=0)
    bvp = ask_int("BvP score vs opp starter: 0=neutral, 1=1-2 hitters 1.000+ OPS, 2=2, 3=3+ hitters 1.000+ OPS (9+PA)", default=0)
    sh = ask_int("Same-handed batters in top 6 vs opposing starter", default=0)
    marquee = ask_bool("Is this team the MARQUEE team drawing public money on national TV?", default=False)

    return TeamData(
        name=name,
        record_w=w, record_l=l,
        home_away="home" if is_home else "away",
        home_w=hw, home_l=hl,
        away_w=aw, away_l=al,
        il_score=il,
        bvp_score=bvp,
        same_handed_top6=sh,
        is_national_tv_marquee=marquee,
    )


def input_game() -> GameData:
    print("\n" + "═" * 60)
    print("  GAME INPUT — MLB Model v2.1")
    print("═" * 60)

    # Teams
    away_team = input_team("Away", is_home=False)
    home_team = input_team("Home", is_home=True)

    # Starters
    away_starter = input_starter("Away")
    home_starter = input_starter("Home")

    # Odds
    print("\n  ── ODDS ──")
    away_ml = ask_ml(f"{away_team.name} moneyline")
    home_ml = ask_ml(f"{home_team.name} moneyline")
    ou_line = ask_float("O/U line", default=8.0)
    ou_dir = ask("O/U bet direction (over/under/skip)", default="skip")

    # Venue / weather
    print("\n  ── VENUE & WEATHER ──")
    park = ask("Park name (e.g. Coors Field, Petco Park)", default="Unknown")
    is_dome = ask_bool("Dome / retractable closed?", default=False)
    temp = ask_float("Temperature (°F)", default=72.0)
    wind = ask_float("Wind speed (mph)", default=0.0)
    wind_dir = ask("Wind direction (out/in/crosswind/calm)", default="calm")
    rain_pct = ask_float("Rain chance (%)", default=0.0)
    rain_flag = ask_bool("Rain flagged by ANY source?", default=False)
    is_turf = ask_bool("Turf surface?", default=False)

    # Context
    print("\n  ── CONTEXT ──")
    ump_favor = ask_float("Umpire run favor (+=hitter, -=pitcher, 0=neutral)", default=0.0)
    series_num = ask_int("Game # in series (1/2/3/4)", default=1)
    nat_tv = ask_bool("National TV game (Apple TV / ESPN / ABC / NBC)?", default=False)
    blowout = ask("Day-after-blowout: which team won by 10+ yesterday? (away/home/none)", default="none")
    blowout_team = None if blowout == "none" else blowout

    tz_disp = ask_int("Away team TZ displacement (e.g. 3 = west coast team going east)", default=0)
    early = ask_bool("Early start (before 2pm local time)?", default=False)

    return GameData(
        away_team=away_team,
        home_team=home_team,
        away_starter=away_starter,
        home_starter=home_starter,
        away_ml=away_ml,
        home_ml=home_ml,
        ou_line=ou_line,
        ou_direction=ou_dir,
        park=park,
        is_dome=is_dome,
        temp_f=temp,
        wind_mph=wind,
        wind_direction=wind_dir,
        rain_pct=rain_pct,
        rain_flagged_any_source=rain_flag,
        is_turf=is_turf,
        ump_run_favor=ump_favor,
        series_game_num=series_num,
        is_national_tv=nat_tv,
        day_after_blowout_team=blowout_team,
        away_tz_displacement=tz_disp,
        is_early_game=early,
    )


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    batch = "--batch" in sys.argv
    results = []

    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║       MLB BETTING MODEL v2.1  |  bitskyb@gmail.com      ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("  Rules from: mlb_model_v2_june28_2026.md")
    print("  Steps 1–11 implemented. Type Ctrl+C to quit.\n")

    while True:
        try:
            game = input_game()
        except KeyboardInterrupt:
            print("\n\nExiting.")
            break

        result = run_model(game)
        results.append(result)
        print("\n" + format_result(result))

        if not batch:
            another = input("\n  Run another game? (y/n): ").strip().lower()
            if another != "y":
                break
        else:
            another = input("\n  Add another game? (y/n): ").strip().lower()
            if another != "y":
                break

    # Batch summary
    if batch and len(results) > 1:
        print("\n" + "═" * 60)
        print("  SLATE SUMMARY")
        print("═" * 60)
        all_picks = []
        for r in results:
            for side, team, ml, conv, units, edge in [
                ("away", r['away_team'], r['away_ml'], r['away_conviction'], r['away_units'], r['away_edge']),
                ("home", r['home_team'], r['home_ml'], r['home_conviction'], r['home_units'], r['home_edge']),
            ]:
                if conv not in ("NO PLAY", "SKIP") and units > 0:
                    ml_str = f"+{ml}" if ml > 0 else str(ml)
                    all_picks.append((team, ml_str, conv, units, edge))

        all_picks.sort(key=lambda x: x[4], reverse=True)

        if all_picks:
            print(f"\n  {len(all_picks)} pick(s) with edge:\n")
            for team, ml, conv, units, edge in all_picks:
                print(f"  {team:22s} {ml:6s} ML  {conv:12s}  {units}u  Edge: {edge:+.1%}")
        else:
            print("\n  No plays with sufficient edge today.")

        total_units = sum(p[3] for p in all_picks)
        print(f"\n  Total units in action: {total_units:.2f}u")


if __name__ == "__main__":
    main()
