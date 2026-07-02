@echo off
python "%~dp0mlb_train.py"
echo.
echo Exit code: %ERRORLEVEL%
pause
