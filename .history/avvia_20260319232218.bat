@echo off
chcp 65001 >nul
title Download Organizer

echo.
echo  === Download Organizer Setup ===
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERRORE] Python non trovato.
    pause
    exit /b 1
)

echo  [1/3] Python trovato.
echo  [2/3] Installazione dipendenze...
pip install -r "%~dp0requirements.txt" --quiet 2>nul
echo  [3/3] Dipendenze installate.
echo.
echo  Avvio organizer...
echo  Premi Ctrl+C per fermare, Ctrl+Shift+O per scansione manuale
echo.

python -W ignore "%~dp0organizer.py"
pause