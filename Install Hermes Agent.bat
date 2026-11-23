@echo off
cd /d "%~dp0"
python scripts/install_native_hermes.py
if errorlevel 1 (
  echo Installation was not confirmed. Please keep the error message for troubleshooting.
) else (
  echo Native Hermes is ready. Start BeLive and test the connection.
)
pause
