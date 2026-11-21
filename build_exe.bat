@echo off
REM Genera dist\KaraokeEasy\KaraokeEasy.exe (ejecutar despues de instalar.bat)
cd /d %~dp0
call .venv\Scripts\activate
pip install pyinstaller
pyinstaller --noconfirm --windowed --name KaraokeEasy ^
  --collect-all demucs --collect-all faster_whisper --collect-all ctranslate2 ^
  --collect-all imageio_ffmpeg --collect-data librosa --collect-all soxr ^
  run.py
echo Ejecutable en dist\KaraokeEasy\KaraokeEasy.exe
pause
