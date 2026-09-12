@echo off
REM Lance PyBuilder sous Windows (crée l'environnement virtuel au premier démarrage).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Premiere utilisation : creation de l'environnement virtuel...
    python -m venv .venv || goto :erreur
    ".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :erreur
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :erreur
)

start "" ".venv\Scripts\pythonw.exe" pybuilder.py %*
exit /b 0

:erreur
echo.
echo L'installation a echoue. Verifiez que Python est installe et present dans le PATH.
pause
exit /b 1
