@echo off
title CS2 AI Vision Launcher
cd /d "C:\Users\Administrator\Documents\ai-faceit"

echo =====================================================================
echo    CS2 AI VISION ENGINE - MASTER LAUNCHER
echo =====================================================================
echo.
echo [1] MODERN GUI CONTROL PANEL (Dark UI, Real-time Sliders, Engine Status)
echo [2] HEADLESS MODE            (Ultra-fast, Zero Windows, Zero Click Block)
echo [3] OVERLAY MODE             (Transparent Visual Boxes + FOV Circle)
echo.
set /p mode="Enter choice [1, 2 or 3] (Default 1): "
if "%mode%"=="" set mode=1

if "%mode%"=="1" (
    echo [*] Starting Modern GUI Control Panel...
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "C:\Users\Administrator\Documents\ai-faceit\gui_panel.py"
) else if "%mode%"=="2" (
    echo [*] Starting Headless Mode...
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "C:\Users\Administrator\Documents\ai-faceit\headless_aim_rcs.py"
) else (
    echo [*] Starting Overlay Mode with Click-Through Fix...
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "C:\Users\Administrator\Documents\ai-faceit\local_aim_esp.py"
)

pause
