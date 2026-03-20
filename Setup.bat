@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  === Download Organizer SETUP ===
echo.
python config\setup_wizard.py
pause
