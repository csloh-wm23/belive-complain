@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required. Install it and try again.
  pause
  exit /b 1
)
rem Run Python in its own console so Ctrl+C never reaches a waiting batch job.
start "BeLive tenant support" python "%~dp0server.py" %*
exit /b
