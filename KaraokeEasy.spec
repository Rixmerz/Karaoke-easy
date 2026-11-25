# -*- mode: python -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files

import os
# Motor GPU (docs/gpu.md): KARAOKE_GPU=1 con torch CUDA instalado -> dist/KaraokeEngine-GPU.
# Solo hace de proceso de trabajo: sin modelos (usa los del motor CPU) ni interfaz.
GPU = os.environ.get("KARAOKE_GPU") == "1"
datas, binaries, hidden = ([("VERSION", ".")] if GPU else [("models", "models"), ("VERSION", "."), ("ui", "ui")]), [], []
# Edición (karaoke_easy/edition.py): el CI escribe EDITION ("steam") antes de construir.
STEAM = os.path.exists("EDITION") and open("EDITION").read().strip().lower() == "steam"
if os.path.exists("EDITION"):
    datas.append(("EDITION", "."))
pkgs = (["torch"] if GPU else []) + ["demucs", "faster_whisper", "ctranslate2", "imageio_ffmpeg", "soxr", "onnxruntime", "julius", "openunmix", "torchaudio"]
if not STEAM:  # la versión Steam no descarga enlaces: sin yt-dlp ni Deno (el Motor GPU sí los lleva: el trabajo descarga el enlace)
    pkgs += ["yt_dlp", "yt_dlp_ejs", "deno"]
for pkg in pkgs:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hidden += h
    except Exception:
        pass
datas += collect_data_files("librosa") + collect_data_files("lazy_loader")
# Deno (motor JavaScript que yt-dlp necesita para YouTube): el paquete pip lo deja como ejecutable
# en Scripts/, fuera del paquete, así que se añade explícitamente.
if not STEAM:
    import deno as _deno
    binaries += [(_deno.find_deno_bin(), "deno")]
hidden += ["sklearn.utils._typedefs", "sklearn.neighbors._partition_nodes", "scipy.special.cython_special"]

a = Analysis(["run.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=["matplotlib", "IPython", "tensorboard", "torchvision"] + (["yt_dlp", "yt_dlp_ejs", "deno"] if STEAM else []), noarchive=False)
pyz = PYZ(a.pure)
NAME = "KaraokeEngine-GPU" if GPU else "KaraokeEngine"
# Motor sin ventana propia: la app Tauri lo lanza con CREATE_NO_WINDOW y lee su salida
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name=NAME)
