@echo off
setlocal
cd /d "%~dp0"

echo Reading GitHub token from .env...
set "GH_TOKEN="
for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env") do (
    if /i "%%a"=="GITHUB_TOKEN" set "GH_TOKEN=%%b"
)
if not defined GH_TOKEN (
    echo   ERROR: GITHUB_TOKEN not found in .env — add GITHUB_TOKEN=ghp_xxx and retry.
    pause
    exit /b 1
)

echo Cleaning up any previous git setup...
if exist .git rmdir /s /q .git

echo Initializing git repo...
git init
git branch -M main

echo Configuring git identity...
git config user.email "bitskyb@gmail.com"
git config user.name "bbitsky"

echo Staging files (excluding problematic paths)...
git add --ignore-errors .

echo Committing...
git commit -m "MLB daily betting research workflow update %date%"

echo Pushing to GitHub with token (no login prompt)...
REM Token is embedded in the push URL so Git never falls back to the interactive
REM credential prompt. The remote is set WITHOUT the token so it isn't stored in
REM .git/config; the token only lives in this one push command.
git remote add origin https://github.com/bbitsky/MLB-Daily.git
REM user:token form — the PAT must be the PASSWORD, not the username, or GitHub
REM rejects it with "Password authentication is not supported".
git push --force "https://bbitsky:%GH_TOKEN%@github.com/bbitsky/MLB-Daily.git" main
if errorlevel 1 (
    echo.
    echo   Push failed. If it says "Invalid username or token", your token in .env
    echo   is expired — generate a new classic PAT with 'repo' scope and update .env.
    pause
    exit /b 1
)

echo.
echo Done! Visit https://github.com/bbitsky/MLB-Daily
endlocal
pause
