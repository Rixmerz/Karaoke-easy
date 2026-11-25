"""Edición de la app: "direct" (venta directa, por defecto) o "steam".

Única fuente de verdad. Se fija al construir: el CI escribe un archivo `EDITION` (con
"steam") que PyInstaller empaqueta junto a VERSION. Sin archivo, la edición es "direct".
La variable de entorno KARAOKE_EDITION la reemplaza (desarrollo y pruebas).

Diferencias de la edición Steam:
  * sin descargas desde enlaces (YouTube u otros): solo archivos locales e importar .karaoke;
  * la licencia personal la da Steam (estado "steam"); solo Eventos usa clave de Lemon Squeezy;
  * sin actualizador propio: las actualizaciones las entrega Steam.
"""
import os
from pathlib import Path

DIRECT, STEAM = "direct", "steam"
EDITIONS = (DIRECT, STEAM)


def _from_file():
    from . import paths
    for c in (paths.app_dir() / "EDITION", Path(__file__).resolve().parent.parent / "EDITION"):
        try:
            return c.read_text(encoding="utf-8").strip().lower()
        except OSError:
            pass
    return None


def current() -> str:
    e = (os.environ.get("KARAOKE_EDITION") or _from_file() or DIRECT).strip().lower()
    return e if e in EDITIONS else DIRECT


def is_steam() -> bool:
    return current() == STEAM


def features() -> dict:
    """Lo que la interfaz necesita saber de la edición."""
    steam = is_steam()
    return {"edition": current(), "url_downloads": not steam, "updater": not steam,
            "license_ui": not steam}


def is_url(x) -> bool:
    from .downloader import is_url as _is_url  # misma regla que usa el procesamiento
    return _is_url(x)
