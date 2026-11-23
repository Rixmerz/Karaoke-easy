"""Descarga desde un enlace (YouTube y otros sitios que soporta yt-dlp)."""
import glob
import os
import re
import sys
from pathlib import Path

from . import paths

URL_RE = re.compile(r"^(https?://|www\.)", re.I)


def is_url(s: str) -> bool:
    return bool(URL_RE.match((s or "").strip()))


def deno_path():
    """Deno (motor JavaScript que yt-dlp necesita para YouTube), incluido en el instalador."""
    cands = []
    if getattr(sys, "frozen", False):
        cands += glob.glob(str(paths.app_dir() / "**" / "deno.exe"), recursive=True)
    try:
        import deno

        cands.append(deno.find_deno_bin())
    except Exception:
        pass
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


class _Logger:
    """Reenvía avisos y errores de yt-dlp al registro del trabajo (Detalles técnicos)."""
    def __init__(self, log):
        self.log = log

    def debug(self, msg):
        if msg.startswith("[download] Destination") or msg.startswith("[Merger]"):
            self.log(msg)

    def info(self, msg):
        pass

    def warning(self, msg):
        self.log("Aviso: " + msg)

    def error(self, msg):
        self.log("Error: " + msg)


class Stalled(Exception):
    pass


def download(url: str, out_dir, want_video=True, log=print, progress=lambda p: None, status=lambda d: None,
             stall_seconds=120):
    """Descarga el enlace en out_dir. Devuelve (ruta_archivo, artista, título)."""
    import imageio_ffmpeg
    import yt_dlp

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    url = url.strip()
    if url.lower().startswith("www."):
        url = "https://" + url

    import time
    last = {"bytes": -1, "t": time.time()}

    def hook(d):
        st = d.get("status")
        if st == "downloading":
            got = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            now = time.time()
            if got > last["bytes"]:
                last["bytes"], last["t"] = got, now
            elif now - last["t"] > stall_seconds:
                raise Stalled(f"La descarga no avanza desde hace {stall_seconds} s (¿conexión lenta o YouTube bloqueando?).")
            if total:
                progress(min(1.0, got / total))
            status({"phase": "download", "fraction": (got / total) if total else None, "bytes": got, "total": total,
                    "speed": d.get("speed"), "eta": d.get("eta"),
                    "part": d.get("info_dict", {}).get("format_id")})
        elif st == "finished":
            status({"phase": "merge"})
            log("Descarga terminada, preparando archivo…")

    # el video solo se usa como fondo desenfocado: 720p basta y descarga mucho más rápido
    fmt = ("bv*[height<=720][ext=mp4]+ba[ext=m4a]/bv*[height<=720]+ba/b[height<=720]/b"
           if want_video else "ba/b")
    opts = {
        "format": fmt,
        "outtmpl": str(out_dir / "%(artist,uploader|desconocido)s - %(track,title)s.%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "progress_hooks": [hook],
        "quiet": True,
        "noprogress": True,
        "logger": _Logger(log),
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
    }
    d = deno_path()
    if d:
        opts["js_runtimes"] = {"deno": {"path": d}}
    log(f"Descargando {url} …")
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if "entries" in info:  # por si es una lista: primer vídeo
            info = next(e for e in info["entries"] if e)
        path = Path(info["requested_downloads"][0]["filepath"]) if info.get("requested_downloads") \
            else Path(ydl.prepare_filename(info))
    artist = info.get("artist") or info.get("creator") or ""
    title = info.get("track") or ""
    if not title:  # "Artista - Tema (Official Video)" en el título del vídeo
        from .lyrics import guess_artist_title

        a, t = guess_artist_title(info.get("title") or path.stem)
        artist = artist or a
        title = t
    artist = re.sub(r"(?i)\s*-\s*topic$|vevo$", "", artist).strip()
    log(f"Descargado: {path.name}")
    return path, artist, title
