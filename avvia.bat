@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo  === Download Organizer ===
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERRORE] Python non trovato.
    pause
    exit /b 1
)

echo  [1/3] Installazione dipendenze...
pip install -r "%~dp0requirements.txt" --quiet 2>nul
tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
if %errorlevel% neq 0 (
    echo  [2/3] Avvio Ollama...
    start "" /b ollama serve
    timeout /t 5 /nobreak >nul
) else (
    echo  [2/3] Ollama gia attivo.
)

timeout /t 5 /nobreak >nul
echo  [3/3] Avvio organizer...

taskkill /f /fi "WINDOWTITLE eq download_organizer*" >nul 2>&1
wmic process where "commandline like '%%organizer.py%%'" delete >nul 2>&1

start "" /b pythonw -W ignore "%~dp0organizer.py"