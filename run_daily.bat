@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "C:\Users\bitsk\Claude\Projects\MLB Daily"

echo ============================================
echo  Step 1: Running daily picks...
echo ============================================
python mlb_daily.py

echo.
echo ============================================
echo  Step 2: Generating HTML dashboard...
echo ============================================
python mlb_dashboard.py --open

echo.
echo ============================================
echo  Step 3: Deploying to GitHub Pages...
echo  (Skipped silently if GITHUB_REPO_URL not set)
echo ============================================
python deploy_dashboard.py
pause
