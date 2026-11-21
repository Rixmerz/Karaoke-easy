@echo off
REM Instala dependencias en un entorno virtual (requiere Python 3.10-3.12 de python.org)
cd /d %~dp0
py -3 -m venv .venv || python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
REM Para GPU NVIDIA, reemplace la siguiente linea por:
REM pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
echo.
echo Instalacion completa. Ejecute KaraokeEasy.bat
pause
