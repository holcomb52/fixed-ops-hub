@echo off
title Fixed Ops Hub
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0open-fixed-ops-hub.ps1"
if errorlevel 1 (
    echo.
    echo Fixed Ops Hub did not start.
    echo Run SETUP-WINDOWS.bat in the main project folder first.
    echo.
    pause
)
