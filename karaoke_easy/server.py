"""Servidor HTTP local (solo 127.0.0.1) que alimenta al reproductor propio."""
import json
import mimetypes
import os
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import library, music

STATIC = Path(__file__).resolve().parent / "player"
_pitch_lock = threading.Lock()


class Songs:
    def __init__(self, extra_dirs=()):
        self.extra_dirs = list(extra_dirs)

    def all(self):
        return library.list_songs(self.extra_dirs)

    def folder(self, sid):
        for s in self.all():
            if s["id"] == sid:
                return Path(s["folder"])
        return None


def render_pitch(folder: Path, st: int, run_ffmpeg):
    """Crea inst_+N.m4a y voz_+N.m4a (transpuestos) si no existen."""
    import soundfile as sf
    import tempfile
    import numpy as np

    out = {}
    for stem in ("inst", "voz"):
        target = folder / f"{stem}_{st:+d}.m4a"
        if not target.exists():
            with tempfile.TemporaryDirectory() as td:
                wav = os.path.join(td, "a.wav")
                run_ffmpeg(["-i", str(folder / f"{stem}.m4a"), "-ac", "2", "-ar", "44100", wav])
                y, sr = sf.read(wav, dtype="float32", always_2d=True)
                z = music.pitch_shift(y.T, sr, st).T
                peak = float(np.abs(z).max()) or 1.0
                if peak > 0.99:
                    z *= 0.99 / peak
                sf.write(wav, z, sr)
                run_ffmpeg(["-i", wav, "-c:a", "aac", "-b:a", "192k", str(target)])
        out[stem] = target.name
    return out


def make_handler(songs: Songs, run_ffmpeg):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def _file(self, path: Path):
            if not path.is_file():
                return self.send_error(404)
            size = path.stat().st_size
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            if path.suffix == ".m4a":
                ctype = "audio/mp4"
            rng = self.headers.get("Range")
            start, end = 0, size - 1
            if rng:
                m = re.match(r"bytes=(\d*)-(\d*)", rng)
                if m:
                    if m.group(1):
                        start = int(m.group(1))
                        end = int(m.group(2)) if m.group(2) else size - 1
                    else:  # sufijo: últimos N bytes
                        start = max(0, size - int(m.group(2)))
                end = min(end, size - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    return self.end_headers()
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            try:
                with open(path, "rb") as f:
                    f.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = f.read(min(1 << 16, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            parts = [urllib.parse.unquote(p) for p in u.path.split("/") if p]
            try:
                if not parts:
                    return self._file(STATIC / "index.html")
                if parts[0] == "static" and len(parts) == 2 and "/" not in parts[1] and ".." not in parts[1]:
                    return self._file(STATIC / parts[1])
                if parts[0] == "api":
                    if parts[1:] == ["library"]:
                        return self._json(songs.all())
                    folder = songs.folder(q.get("id", [""])[0])
                    if folder is None:
                        return self._json({"error": "canción no encontrada"}, 404)
                    if parts[1:] == ["song"]:
                        meta = json.loads((folder / library.SONG).read_text(encoding="utf-8"))
                        meta["id"] = q["id"][0]
                        meta["has_video"] = bool(meta.get("video") and Path(meta["video"]).exists())
                        return self._json(meta)
                    if parts[1:] == ["pitch"]:
                        st = max(-12, min(12, int(q.get("st", ["0"])[0])))
                        if st == 0:
                            return self._json({"inst": "inst.m4a", "voz": "voz.m4a"})
                        with _pitch_lock:
                            return self._json(render_pitch(folder, st, run_ffmpeg))
                if parts[0] == "media" and len(parts) == 3:
                    folder = songs.folder(parts[1])
                    if folder is None:
                        return self.send_error(404)
                    if parts[2] == "video":
                        meta = json.loads((folder / library.SONG).read_text(encoding="utf-8"))
                        return self._file(Path(meta.get("video") or ""))
                    name = parts[2]
                    if not re.fullmatch(r"(inst|voz)(_[+-]\d+)?\.m4a", name):
                        return self.send_error(403)
                    return self._file(folder / name)
                self.send_error(404)
            except Exception as e:  # nunca tumbar el servidor
                try:
                    self._json({"error": str(e)}, 500)
                except Exception:
                    pass

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path == "/api/save":
                folder = songs.folder(q.get("id", [""])[0])
                if folder is None:
                    return self._json({"error": "canción no encontrada"}, 404)
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n).decode("utf-8"))
                library.save_lines(folder, body["lines"])
                return self._json({"ok": True})
            self.send_error(404)

    return H


def start(extra_dirs=(), run_ffmpeg=None, port=0):
    if run_ffmpeg is None:
        from .pipeline import run_ffmpeg
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(Songs(extra_dirs), run_ffmpeg))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"
