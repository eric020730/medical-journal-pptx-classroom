@echo off
setlocal
set "PYTHONUTF8=1"
set "PROJECT_ROOT=%~dp0"
set "PROJECT_PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"

if not exist "%PROJECT_PYTHON%" (
  echo Project Python environment is missing. Run setup-windows.cmd first. 1>&2
  exit /b 1
)

"%PROJECT_PYTHON%" "%PROJECT_ROOT%tools\classroom.py" %*
exit /b %ERRORLEVEL%
