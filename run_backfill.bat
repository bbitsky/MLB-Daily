@echo off
cd /d "%~dp0"
echo MLB Feature Backfill
echo ====================
echo.
echo This will add streak, day/night, OPS, and defensive rank data
echo to the historical games database and then retrain the model.
echo.
echo Step 1: Backfilling feature columns...
python mlb_backfill.py
echo.
echo Step 2: Retraining model with new features...
python mlb_train.py
echo.
echo Done! Run run_daily.bat to generate today's picks with updated model.
pause
