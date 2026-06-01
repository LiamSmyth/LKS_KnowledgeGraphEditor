@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please run setup_venv.bat first.
    pause
    exit /b 1
)
.venv\Scripts\python.exe src\lks_utils\knowledge\demo\demo_workbench_ui_gui.py
pause
