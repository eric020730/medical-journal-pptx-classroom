@echo off
setlocal
set "PYTHONUTF8=1"
set "PROJECT_ROOT=%~dp0"
set "PROJECT_PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"

if not exist "%PROJECT_PYTHON%" (
  echo Project Python environment is missing. Ask Codex to follow CODEX-START.md using setup-codex.ps1. 1>&2
  exit /b 1
)

set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "MEDICAL_JOURNAL_PPTX_PYTHON=%PROJECT_PYTHON%"
set "MEDICAL_JOURNAL_PPTX_RUNTIME=%PROJECT_ROOT%.venv"
set "PIXI_HOME=%PROJECT_ROOT%.bootstrap\pixi-home"
set "PIXI_CACHE_DIR=%PROJECT_ROOT%.bootstrap\pixi-cache"
set "PIXI_NO_PATH_UPDATE=1"
set "PATH=%PROJECT_ROOT%.bootstrap\pixi-home\bin;%PROJECT_ROOT%.bootstrap\libreoffice\program;%PATH%"
"%PROJECT_PYTHON%" "%PROJECT_ROOT%tools\classroom.py" %*
exit /b %ERRORLEVEL%
