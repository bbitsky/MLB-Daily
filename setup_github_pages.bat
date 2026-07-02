@echo off
cd /d "%~dp0"
echo Running initial GitHub Pages deploy...
python deploy_dashboard.py --init
echo.
echo Done! Your dashboard should now be live at:
echo https://bbitsky.github.io/MLB-Daily/
echo.
echo (GitHub Pages may take 1-2 minutes to go live after the first deploy)
pause
