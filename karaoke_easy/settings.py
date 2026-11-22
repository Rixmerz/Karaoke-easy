"""Ajustes del usuario (se guardan en %LOCALAPPDATA%\\KaraokeEasy\\ajustes.json)."""
import json
from pathlib import Path

from . import paths

DEFAULTS = {
    "output_dir": str(Path.home() / "Videos" / "Karaoke Easy"),
    "language": None,          # None = automático
    "quality": "1080",         # 720 | 1080
    "guide_track": True,       # pista de voz guía dentro del MP4
    "use_source_video": True,  # usar el vídeo original de fondo si existe
    "make_video": True,        # generar también el MP4 (además del reproductor)
}


def _file():
    return paths.user_cache() / "ajustes.json"


def load():
    s = dict(DEFAULTS)
    try:
        s.update({k: v for k, v in json.loads(_file().read_text(encoding="utf-8")).items() if k in DEFAULTS})
    except Exception:
        pass
    return s


def save(new: dict):
    s = load()
    s.update({k: v for k, v in new.items() if k in DEFAULTS})
    _file().write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    return s
