@echo off
cd /d "%~dp0"
python scripts/knowledge_backup.py runtime
if errorlevel 1 goto failed
python scripts/knowledge_backup.py export
if errorlevel 1 goto failed
python scripts/knowledge_backup.py check
if errorlevel 1 goto failed
git push
if errorlevel 1 goto failed
echo Committed code was pushed. The encrypted knowledge backup stayed on this computer.
echo Share the backup and recovery key only through a private channel.
pause
exit /b 0
:failed
echo Push was not confirmed. Resolve the message above and try again.
pause
exit /b 1
