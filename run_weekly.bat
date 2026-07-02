@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "C:\Users\bitsk\Claude\Projects\MLB Daily"

echo ============================================
echo  Step 1: Pulling 2026 game data...
echo ============================================
python mlb_data.py --build --seasons 2026

echo.
echo ============================================
echo  Step 2: Retraining XGBoost model...
echo ============================================
python mlb_train.py

echo.
echo ============================================
echo  Weekly retrain complete!
echo  Model updated with latest 2026 games.
echo ============================================
pause
