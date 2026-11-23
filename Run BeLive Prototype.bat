@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required. Install it and try again.
  pause
  exit /b 1
)
rem Run Python in its own console so Ctrl+C never reaches a waiting batch job.
python scripts/install_native_hermes.py --check >nul 2>nul
if errorlevel 1 (
  echo Native Hermes Agent is required. Run "Install Hermes Agent.bat" once, then start BeLive again.
  pause
  exit /b 1
)
if exist "knowledge\team-memory.enc.json" (
  python scripts/knowledge_backup.py runtime
  if errorlevel 1 exit /b 1
)
python scripts/knowledge_backup.py install-hooks >nul 2>nul
start "BeLive tenant support" python "%~dp0server.py" %*
exit /b
