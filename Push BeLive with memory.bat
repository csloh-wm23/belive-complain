@echo off
cd /d "%~dp0"
python scripts/knowledge_backup.py runtime
if errorlevel 1 goto failed
python scripts/knowledge_backup.py export
if errorlevel 1 goto failed
git add -- knowledge/team-memory.enc.json
if errorlevel 1 goto failed
git diff --cached --quiet
if errorlevel 1 git commit -m "Save current approved BeLive knowledge backup"
if errorlevel 1 goto failed
git push
if errorlevel 1 goto failed
echo Code and the encrypted knowledge backup were pushed.
pause
exit /b 0
:failed
echo Push was not confirmed. Resolve the message above and try again.
pause
exit /b 1
