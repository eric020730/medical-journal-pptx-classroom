@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo First run setup-windows.cmd in this folder.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" "tools\classroom_preflight.py"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
