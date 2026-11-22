# -*- mode: python -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas, binaries, hidden = [("models", "models")], [], []
for pkg in ["demucs", "faster_whisper", "ctranslate2", "imageio_ffmpeg", "soxr", "onnxruntime", "julius", "openunmix", "torchaudio", "yt_dlp", "yt_dlp_ejs", "deno"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hidden += h
    except Exception:
        pass
datas += collect_data_files("librosa") + collect_data_files("lazy_loader")
# Deno (motor JavaScript que yt-dlp necesita para YouTube): el paquete pip lo deja como ejecutable
# en Scripts/, fuera del paquete, así que se añade explícitamente.
import deno as _deno
binaries += [(_deno.find_deno_bin(), "deno")]
hidden += ["sklearn.utils._typedefs", "sklearn.neighbors._partition_nodes", "scipy.special.cython_special"]

a = Analysis(["run.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=["matplotlib", "IPython", "tensorboard", "torchvision"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="KaraokeEasy", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="KaraokeEasy")
