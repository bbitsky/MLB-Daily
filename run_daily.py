"""run_daily.py — log yesterday's picks and regenerate dashboard."""
import sys, shutil, importlib.util, tempfile, atexit, argparse, platform, sqlite3
from pathlib import Path; from datetime import date, timedelta

P = Path(__file__).parent
PYCS = P / "__pycache__"

def load(name):
    """Import a project module robustly across environments.

    Prefers the .py source (always compatible with the running interpreter). On
    the Linux/FUSE sandbox the source can arrive truncated mid-sync, so we fall
    back to a prebuilt .pyc — using this interpreter's own cache tag rather than
    a hard-coded version, then any other .pyc as a last resort.
    """
    py = P / f"{name}.py"
    on_fuse = platform.system() == "Linux" and " " in str(P)

    def _imp(src):
        spec = importlib.util.spec_from_file_location(name, src)
        mod  = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    ver_pyc = Path(importlib.util.cache_from_source(str(py)))  # matches this Python
    cands = []
    if py.exists():      cands.append(py)
    if ver_pyc.exists(): cands.append(ver_pyc)
    if PYCS.exists():    cands += sorted(PYCS.glob(f"{name}.*.pyc"))
    if on_fuse and ver_pyc.exists():          # sandbox: matching .pyc dodges truncation
        cands = [ver_pyc] + [c for c in cands if c != ver_pyc]

    seen, ordered = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c); ordered.append(c)

    last = None
    for src in ordered:
        try:
            return _imp(src)
        except Exception as e:
            last = e
            sys.modules.pop(name, None)
    raise ImportError(f"could not load {name} from {[str(c) for c in ordered]}: {last}")

sys.path.insert(0, str(P))
mdata = load("mlb_data"); mres = load("mlb_results"); mdash = load("mlb_dashboard")

def check_db_health(db_path):
    """Fail fast if the DB is missing, malformed, or locked mid-write."""
    if not db_path.exists():
        print(f"  [DB CHECK] {db_path} not found — run your data pull or repair_mlb_db.py first.", file=sys.stderr)
        sys.exit(1)
    stale = [j.name for j in (db_path.with_suffix(".db-journal"), db_path.with_suffix(".db-wal")) if j.exists()]
    try:
        con = sqlite3.connect(str(db_path), timeout=3)
        status = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
    except Exception as e:
        status = f"error: {e}"
    if status != "ok":
        print("\n" + "!" * 60, file=sys.stderr)
        print("  [DB CHECK] data/mlb.db FAILED integrity check — aborting.", file=sys.stderr)
        print(f"            status: {status}", file=sys.stderr)
        if stale:
            print(f"            stale {', '.join(stale)} present -> the DB is likely LOCKED", file=sys.stderr)
            print("            by a running app mid-write. Close the MLB app / any DB", file=sys.stderr)
            print("            browser, then re-run this script.", file=sys.stderr)
        print("            If it stays broken: python repair_mlb_db.py", file=sys.stderr)
        print("!" * 60 + "\n", file=sys.stderr)
        sys.exit(2)
    if stale:
        print(f"  [DB CHECK] Warning: stale {', '.join(stale)} present, but DB reads ok.", file=sys.stderr)
    print("  [DB CHECK] data/mlb.db integrity ok.", file=sys.stderr)

orig = P / "data" / "mlb.db"
# Health-check the DB ACTUALLY IN USE, not the synced project backup. mlb_data
# relocates the live DB off the synced folder (LocalAppData on Windows); the
# project data/mlb.db is only a backup and is frequently an empty/corrupt husk.
# Checking it here used to sys.exit() and abort the whole daily run — including
# dashboard regeneration — even when the live DB was perfectly healthy.
live_db = Path(getattr(mdata, "DB_PATH", orig))
check_db_health(live_db)
if platform.system() == "Linux" and " " in str(orig) and orig.exists():
    tmp = Path(tempfile.mkdtemp(prefix="mlb_db_")) / "mlb.db"
    shutil.copy2(str(orig), str(tmp))
    atexit.register(lambda: shutil.copy2(str(tmp), str(orig)))
    for m in (mdata, mres, mdash):
        if hasattr(m, "DB_PATH"): m.DB_PATH = tmp
    print(f"  [DB] shadow -> {tmp}", file=sys.stderr)

ap = argparse.ArgumentParser(); ap.add_argument("--date"); ap.add_argument("--no-dashboard", action="store_true")
args = ap.parse_args(); tgt = args.date or (date.today() - timedelta(days=1)).isoformat()

print(f"\n[1] Logging results for {tgt}...")
s = mres.auto_log_results(tgt, verbose=True)

try:
    import sync_bets
    _jp = sync_bets._find_json(None)
    if _jp.exists():
        _m, _miss = sync_bets.apply(mres.DB_PATH, _jp)
        print(f"  [bets] synced {_m} bet flag(s) from {_jp.name}")
except Exception as _e:
    print(f"  [bets] sync skipped: {_e}")

if not args.no_dashboard:
    today = date.today().isoformat(); pr2 = mres.get_pick_record(); rec = mdash.compute_model_record()
    bd2 = mres.get_bankroll_data()
    # Load the LOCKED picks for the Picks tab — never recompute from live odds on
    # a rebuild. Live/current odds are a separate read-only tab.
    try:
        import mlb_freeze
        frozen_picks = mlb_freeze.load_frozen(today, str(P)) or []
        if frozen_picks:
            print(f"  [freeze] loaded {len(frozen_picks)} locked picks for {today}")
        else:
            print(f"  [freeze] no snapshot for {today} yet — run the morning build first.")
    except Exception as _e:
        frozen_picks = []
        print(f"  [freeze] load skipped: {_e}")
    # Real betting/social intel (weather, line movement, book disagreement,
    # injuries). Degrades to None if the data sources are unavailable.
    bettor_news = social_intel = None
    try:
        import mlb_intel
        bettor_news, social_intel = mlb_intel.generate_intel(today, db=str(mdata.DB_PATH))
        print(f"  [intel] bettor={len(bettor_news or [])} social={len(social_intel or [])}")
    except Exception as _e:
        print(f"  [intel] skipped: {_e}")
    html = mdash.generate_html(picks=frozen_picks, record=rec, today=today, pick_record=pr2,
                               bankroll_data=bd2, bettor_news=bettor_news, social_intel=social_intel)
    out = P / f"mlb_dashboard_{today}.html"
    try:
        import mlb_edge as _E
        if hasattr(_E, "inject_health_banner"):
            html = _E.inject_health_banner(html, frozen_picks)
    except Exception:
        pass
    out.write_text(html, encoding="utf-8")
    print(f"\n[2] Dashboard -> {out.name} ({len(html):,} bytes)")

pr = mres.get_pick_record(); t = pr["total"]; bank = 500 + t["pl"] * 50
print(f"\n{'='*48}")
print(f"  Date: {tgt}  Resolved: {s.get('resolved',0)}  ({s.get('wins',0)}W-{s.get('losses',0)}L)  P/L: {s.get('pl',0):+.3f}u")
print(f"  Session: {t['wins']}W-{t['losses']}L ({t['win_pct']:.1%})  Total: {t['pl']:+.2f}u  Bankroll: ${bank:.2f}")
print(f"{'='*48}")
