@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\install_schedule.ps1"
if errorlevel 1 exit /b 1
pause
