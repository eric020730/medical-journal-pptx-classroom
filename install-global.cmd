@echo off
setlocal
set "PYTHONUTF8=1"
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0install-global.ps1" %*
exit /b %ERRORLEVEL%
