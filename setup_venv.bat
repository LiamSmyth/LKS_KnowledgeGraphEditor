@echo off
setlocal
cd /d "%~dp0"
echo Creating virtual environment...
python -m venv .venv
if errorlevel 1 (echo Failed to create virtual environment & pause & exit /b 1)
echo.
echo Installing sandbox requirements...
.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (echo pip install failed & pause & exit /b 1)
echo.
if defined LKS_UTILS_PATH (
    echo Installing lks_utils from local path: %LKS_UTILS_PATH%
    .venv\Scripts\pip install -e "%LKS_UTILS_PATH%[gui-qt,knowledge]"
    if errorlevel 1 (echo lks_utils install failed & pause & exit /b 1)
) else (
    echo WARNING: LKS_UTILS_PATH is not set.
    echo          lks_utils was not installed. Set LKS_UTILS_PATH and re-run,
    echo          or install manually:  .venv\Scripts\pip install lks-utils[gui-qt,knowledge]
)
echo.
echo Setup complete. Run run.bat to launch.
pause
