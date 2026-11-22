"""Rutas de los modelos incluidos en el programa (funciona en desarrollo y en el .exe)."""
import os
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def _user_cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "KaraokeEasy"


def _models_dir() -> Path:
    """Modelos incluidos en el instalador completo; si no están (instalador ligero),
    los descargados en la carpeta del usuario."""
    if os.environ.get("KARAOKE_MODELS"):
        return Path(os.environ["KARAOKE_MODELS"])
    bundled = app_dir() / "models"
    if (bundled / "demucs" / "htdemucs.yaml").exists():
        return bundled
    return _user_cache_dir() / "models"


MODELS_DIR = _models_dir()
BUNDLED_MODELS = MODELS_DIR == app_dir() / "models"


def models_ready() -> bool:
    return ((MODELS_DIR / "demucs" / "htdemucs.yaml").exists() and (MODELS_DIR / "mms_fa_fp16.pt").exists()
            and bool(bundled_whisper_models()))
TORCH_HOME = MODELS_DIR / "torch"  # solo al preparar los modelos (tools/download_models.py)
DEMUCS_DIR = MODELS_DIR / "demucs"  # htdemucs.yaml + <firma>.th: se carga directo, sin torch.hub


def user_cache() -> Path:
    """Carpeta escribible del usuario. El programa NUNCA escribe en su carpeta de instalación
    (C:\\Program Files es de solo lectura sin permisos de administrador)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    p = Path(base) / "KaraokeEasy"
    p.mkdir(parents=True, exist_ok=True)
    return p


def setup_offline():
    """Cachés de librerías en la carpeta del usuario; los modelos incluidos se leen directamente."""
    if not (DEMUCS_DIR / "htdemucs.yaml").exists() and (TORCH_HOME / "hub").exists():
        os.environ["TORCH_HOME"] = str(TORCH_HOME)  # instalación antigua/desarrollo
    else:
        os.environ["TORCH_HOME"] = str(user_cache() / "torch")
    os.environ.setdefault("HF_HOME", str(user_cache() / "huggingface"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1" if bundled_whisper_models() else "0")


def whisper_dir(name: str) -> Path:
    return MODELS_DIR / f"whisper-{name}"


def bundled_whisper_models():
    order = ["tiny", "base", "small", "medium", "large-v3"]
    return [m for m in order if (whisper_dir(m) / "model.bin").exists()]


def app_version() -> str:
    for c in (app_dir() / "VERSION", Path(__file__).resolve().parent.parent / "VERSION"):
        try:
            return c.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return "0"
