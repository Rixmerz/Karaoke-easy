"""Rutas de los modelos incluidos en el programa (funciona en desarrollo y en el .exe)."""
import os
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


MODELS_DIR = Path(os.environ.get("KARAOKE_MODELS", app_dir() / "models"))
TORCH_HOME = MODELS_DIR / "torch"  # contiene hub/checkpoints/<pesos de htdemucs>.th


def setup_offline():
    """Hace que Demucs use los pesos incluidos en lugar de descargarlos."""
    os.environ["TORCH_HOME"] = str(TORCH_HOME)
    os.environ.setdefault("HF_HUB_OFFLINE", "1" if bundled_whisper_models() else "0")


def whisper_dir(name: str) -> Path:
    return MODELS_DIR / f"whisper-{name}"


def bundled_whisper_models():
    order = ["tiny", "base", "small", "medium", "large-v3"]
    return [m for m in order if (whisper_dir(m) / "model.bin").exists()]
