@echo off
setlocal
set "PROJECT_ROOT=%~dp0"

where powershell.exe >nul 2>nul
if errorlevel 1 (
  echo Windows PowerShell was not found. Ask your administrator for help. 1>&2
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%PROJECT_ROOT%setup-windows.ps1" %*
set "SETUP_RESULT=%ERRORLEVEL%"
if not "%SETUP_RESULT%"=="0" (
  echo.
  echo Installation failed. Review the message above and docs\TROUBLESHOOTING.md.
  echo If your institution blocks scripts, ask your IT administrator before changing policy.
)
if not defined CI pause
exit /b %SETUP_RESULT%
