"""
deploy_dashboard.py — Push the daily MLB dashboard HTML to GitHub Pages

Usage:
    python deploy_dashboard.py                         # deploys today's dashboard
    python deploy_dashboard.py path/to/dashboard.html  # deploys a specific file

Setup (one-time):
    1. Create a GitHub repo (e.g. "mlb-picks") or use an existing one
    2. Set these in your .env file:
         GITHUB_REPO_URL=https://github.com/YOUR_USERNAME/YOUR_REPO.git
         GITHUB_PAGES_BRANCH=gh-pages          # or "main" if using /docs
         GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx  # Personal Access Token with repo scope
    3. Run: python deploy_dashboard.py --init   (first time only, clones the branch)
    4. Your dashboard will be live at: https://YOUR_USERNAME.github.io/YOUR_REPO/

After initial setup, deploy_dashboard.py is called automatically by:
    - run_daily.bat  (end of daily picks run)
    - mlb_dashboard.py --deploy
"""

import os
import sys
import shutil
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── Config (from .env) ────────────────────────────────────────────────────────
REPO_URL     = os.getenv("GITHUB_REPO_URL", "")
PAGES_BRANCH = os.getenv("GITHUB_PAGES_BRANCH", "gh-pages")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
PROJECT_DIR  = Path(__file__).parent

# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str], cwd: str = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command, print output, raise on failure."""
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.stdout.strip():
        print(f"    {result.stdout.strip()}")
    if result.returncode != 0 and check:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr}")
    return result


def _inject_token(url: str, token: str) -> str:
    """Embed a GitHub PAT into an HTTPS repo URL for auth."""
    if token and "github.com" in url and "@" not in url:
        url = url.replace("https://", f"https://{token}@")
    return url


def _find_dashboard(html_path: str = None) -> Path:
    """Return path to the dashboard HTML to deploy."""
    if html_path:
        p = Path(html_path)
        if not p.exists():
            raise FileNotFoundError(f"Dashboard file not found: {p}")
        return p

    today = date.today().isoformat()
    p = PROJECT_DIR / f"mlb_dashboard_{today}.html"
    if p.exists():
        return p

    # Fall back to most recent dashboard file
    candidates = sorted(PROJECT_DIR.glob("mlb_dashboard_*.html"), reverse=True)
    if candidates:
        return candidates[0]

    raise FileNotFoundError("No dashboard HTML found. Run mlb_dashboard.py first.")


# ── Main deploy logic ─────────────────────────────────────────────────────────

def deploy(html_path: str = None, init: bool = False):
    """
    Clone the gh-pages branch into a temp dir, copy the dashboard in as index.html,
    commit, and push.
    """
    if not REPO_URL:
        print("[Deploy] GITHUB_REPO_URL not set in .env — skipping.")
        print("         Add:  GITHUB_REPO_URL=https://github.com/USER/REPO.git")
        return

    dashboard_file = _find_dashboard(html_path)
    print(f"[Deploy] Deploying: {dashboard_file.name}")

    # Inject token into URL for auth
    auth_url = _inject_token(REPO_URL, GITHUB_TOKEN)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = str(tmp)

        # Check if gh-pages branch exists
        result = _run(
            ["git", "ls-remote", "--heads", auth_url, PAGES_BRANCH],
            check=False
        )
        branch_exists = PAGES_BRANCH in (result.stdout or "")

        if not branch_exists or init:
            # Create the branch from scratch (orphan)
            print(f"[Deploy] Creating '{PAGES_BRANCH}' branch...")
            _run(["git", "init", tmp_path])
            _run(["git", "checkout", "--orphan", PAGES_BRANCH], cwd=tmp_path)
            _run(["git", "remote", "add", "origin", auth_url], cwd=tmp_path)
        else:
            # Clone just the gh-pages branch (shallow for speed)
            print(f"[Deploy] Cloning '{PAGES_BRANCH}' branch...")
            _run([
                "git", "clone",
                "--branch", PAGES_BRANCH,
                "--single-branch",
                "--depth", "1",
                auth_url, tmp_path
            ])

        # Copy dashboard as index.html
        dest = Path(tmp_path) / "index.html"
        shutil.copy2(dashboard_file, dest)
        print(f"[Deploy] Copied → index.html")

        # Also copy as dated archive (e.g. 2026-06-29.html)
        dated_name = dashboard_file.name  # already date-stamped
        shutil.copy2(dashboard_file, Path(tmp_path) / dated_name)

        # Write a simple _config.yml if it doesn't exist (disables Jekyll)
        nojekyll = Path(tmp_path) / ".nojekyll"
        if not nojekyll.exists():
            nojekyll.touch()

        # Stage, commit, push
        _run(["git", "config", "user.email", "bitskyb@gmail.com"], cwd=tmp_path)
        _run(["git", "config", "user.name",  "MLB Model Bot"],      cwd=tmp_path)
        _run(["git", "add", "-A"], cwd=tmp_path)

        commit_msg = f"Dashboard update {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        result = _run(
            ["git", "commit", "-m", commit_msg],
            cwd=tmp_path, check=False
        )
        if "nothing to commit" in (result.stdout + result.stderr):
            print("[Deploy] Nothing changed — already up to date.")
            return

        _run(
            ["git", "push", auth_url, f"HEAD:{PAGES_BRANCH}", "--force"],
            cwd=tmp_path
        )

    # Derive the Pages URL
    pages_url = REPO_URL.replace(".git", "").replace("github.com", "")
    parts = [p for p in pages_url.split("/") if p]
    if len(parts) >= 2:
        user, repo = parts[-2], parts[-1]
        print(f"\n[Deploy] Live at: https://{user}.github.io/{repo}/")
    print(f"[Deploy] Done at {datetime.now().strftime('%H:%M:%S')}")


# ── Init helper: sets up .env entries ────────────────────────────────────────

def setup_env():
    """Interactive first-time setup: prompt for GitHub details and write to .env."""
    env_path = PROJECT_DIR / ".env"
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    print("\nGitHub Pages — First-Time Setup")
    print("=" * 45)
    print("You'll need:")
    print("  1. A GitHub repo (create at https://github.com/new)")
    print("  2. A Personal Access Token with 'repo' scope")
    print("     (Settings → Developer settings → Personal access tokens → Tokens classic)")
    print()

    repo = input("Repo URL (e.g. https://github.com/USERNAME/mlb-picks.git): ").strip()
    token = input("GitHub Personal Access Token (ghp_...): ").strip()
    branch = input("Branch [gh-pages]: ").strip() or "gh-pages"

    # Add/update .env entries
    lines = existing.splitlines()
    new_lines = []
    keys_written = set()
    for line in lines:
        k = line.split("=")[0].strip()
        if k == "GITHUB_REPO_URL":
            new_lines.append(f"GITHUB_REPO_URL={repo}")
            keys_written.add(k)
        elif k == "GITHUB_TOKEN":
            new_lines.append(f"GITHUB_TOKEN={token}")
            keys_written.add(k)
        elif k == "GITHUB_PAGES_BRANCH":
            new_lines.append(f"GITHUB_PAGES_BRANCH={branch}")
            keys_written.add(k)
        else:
            new_lines.append(line)

    if "GITHUB_REPO_URL" not in keys_written:
        new_lines.append(f"GITHUB_REPO_URL={repo}")
    if "GITHUB_TOKEN" not in keys_written:
        new_lines.append(f"GITHUB_TOKEN={token}")
    if "GITHUB_PAGES_BRANCH" not in keys_written:
        new_lines.append(f"GITHUB_PAGES_BRANCH={branch}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"\nSaved to {env_path}")
    print("Running initial deploy...")
    deploy(init=True)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deploy MLB dashboard to GitHub Pages")
    parser.add_argument("file", nargs="?", help="Path to dashboard HTML (default: today's)")
    parser.add_argument("--init",  action="store_true", help="First-time setup wizard")
    parser.add_argument("--setup", action="store_true", help="Interactive .env setup")
    args = parser.parse_args()

    if args.setup or args.init and not REPO_URL:
        setup_env()
    else:
        deploy(html_path=args.file, init=args.init)
