@echo off
title Aggiungi ad Avvio Automatico
color 0B

set SCRIPT_DIR=%~dp0
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set VBS_FILE=%STARTUP%\DownloadOrganizer.vbs

echo.
echo  Aggiunta a Avvio Automatico di Windows...
echo.

:: Crea un .vbs che lancia lo script senza finestra visibile
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.Run "cmd /c python ""%SCRIPT_DIR%organizer.py""", 0, False
) > "%VBS_FILE%"

if exist "%VBS_FILE%" (
    echo  [OK] Aggiunto! L'organizer partira' automaticamente al prossimo login.
    echo  File creato: %VBS_FILE%
) else (
    echo  [ERRORE] Non e' stato possibile aggiungere l'avvio automatico.
)

echo.
pause
