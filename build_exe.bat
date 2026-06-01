@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please run setup_venv.bat first.
    pause
    exit /b 1
)
echo Installing PyInstaller into sandbox venv...
.venv\Scripts\pip install pyinstaller --quiet
if errorlevel 1 (echo PyInstaller install failed & pause & exit /b 1)
echo.
echo Building executable...
.venv\Scripts\pyinstaller --onefile --windowed --name lks_knowledge_graph_editor --hidden-import _cffi_backend --collect-data lks_utils.gui_qt.canvas2d --collect-data lks_utils.gui_qt --collect-data lks_utils.knowledge --collect-data lks_utils.knowledge.ui src\lks_utils\knowledge\demo\demo_workbench_ui_gui.py
if errorlevel 1 (echo Build failed & pause & exit /b 1)
echo.
echo Done. Check dist\ for the built executable.
pause
