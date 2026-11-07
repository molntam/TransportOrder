@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 -m pip install -r requirements-spotfire.txt
) else (
    python -m pip install -r requirements-spotfire.txt
)
if errorlevel 1 (
    echo Spotfire support could not be installed. Check your Python package access.
) else (
    echo Spotfire support installed. Start TransportOrder again.
)
pause
