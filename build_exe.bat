@echo off
REM Construye el instalador completo con modelos incluidos (ejecutar despues de instalar.bat).
REM Requiere Inno Setup 6 (https://jrsoftware.org/isinfo.php) para el paso final.
cd /d %~dp0
call .venv\Scripts\activate
pip install pyinstaller
python tools\download_models.py base small || exit /b 1
pyinstaller --noconfirm KaraokeEasy.spec || exit /b 1
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer\KaraokeEasy.iss
echo Instalador en Output\
pause
