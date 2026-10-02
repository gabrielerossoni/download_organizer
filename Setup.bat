@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  === Download Organizer SETUP ===
echo.
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" config\setup_wizard.py
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import json,sys; cfg=json.load(open('config/config.json',encoding='utf-8')); sys.exit(0 if cfg.get('ai_enabled') and cfg.get('ai_backend','semantic')=='semantic' else 1)"
if errorlevel 1 goto finished
".venv\Scripts\python.exe" -m pip install -r requirements-ai.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" config\install_model.py
if errorlevel 1 goto failed
:finished
pause
exit /b 0
:failed
echo [ERRORE] Setup interrotto. Controlla il messaggio sopra.
pause
exit /b 1
