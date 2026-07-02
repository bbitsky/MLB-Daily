@echo off
chcp 65001 >nul
cd /d "C:\Users\bitsk\Claude\Projects\MLB Daily"

echo ============================================
echo  Auto-logging yesterday's MLB results...
echo ============================================
python mlb_results.py

echo.
echo ============================================
echo  Regenerating dashboard with updated P/L...
echo ============================================
python mlb_dashboard.py --open

pause
