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

def _static_dir():
    from . import paths
    for c in (paths.app_dir() / "ui", Path(__file__).resolve().parent.parent / "ui"):
        if (c / "index.html").exists():
            return c
    return Path(__file__).resolve().parent / "player"


STATIC = _static_dir()
_pitch_lock = threading.Lock()
_render_lock = threading.Lock()


class Songs:
    def __init__(self, extra_dirs=()):
        self.extra_dirs = list(extra_dirs)

    def all(self):
        from . import settings
        dirs = list(self.extra_dirs)
        try:
            dirs.append(settings.load()["output_dir"])
        except Exception:
            pass
        return library.list_songs([d for d in dirs if d and Path(d).exists()])

    def folder(self, sid):
        for s in self.all():
            if s["id"] == sid:
                return Path(s["folder"])
        return None


_RB = None


def _has_rubberband():
    """¿El ffmpeg incluido trae el filtro rubberband (cambio de tono rápido y de calidad)?"""
    global _RB
    if _RB is None:
        try:
            import subprocess
            from .pipeline import ffmpeg_exe, NO_WINDOW
            p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-filters"], capture_output=True,
                               encoding="utf-8", errors="replace", creationflags=NO_WINDOW, timeout=20)
            _RB = " rubberband " in p.stdout
        except Exception:
            _RB = False
    return _RB


def _pitch_filter(st: int) -> str:
    ratio = 2 ** (st / 12)
    if _has_rubberband():
        return f"rubberband=pitch={ratio:.6f}:formant=preserved"
    # Alternativa sin rubberband: cambiar la velocidad de muestreo y compensar el tempo
    return f"asetrate=44100*{ratio:.6f},aresample=44100,atempo={1 / ratio:.6f}"


def render_pitch(folder: Path, st: int, run_ffmpeg):
    """Crea inst_+N.m4a y voz_+N.m4a (transpuestos) si no existen.

    Todo lo hace ffmpeg (sin pasar por Python/numpy), las dos pistas a la vez, y escribe
    a un archivo temporal que solo se renombra al terminar: un intento cortado ya no deja
    un archivo roto que luego se tomaba como hecho."""
    from concurrent.futures import ThreadPoolExecutor

    def one(stem):
        target = folder / f"{stem}_{st:+d}.m4a"
        if not target.exists() or target.stat().st_size < 1024:
            tmp = folder / f"{stem}_{st:+d}.tmp.m4a"
            run_ffmpeg(["-i", str(folder / f"{stem}.m4a"), "-vn", "-ac", "2", "-ar", "44100",
                        "-af", _pitch_filter(st) + ",alimiter=limit=0.98",
                        "-c:a", "aac", "-b:a", "192k", "-f", "mp4", str(tmp)])
            os.replace(tmp, target)
        return stem, target.name

    with ThreadPoolExecutor(2) as ex:
        return dict(ex.map(one, ("inst", "voz")))


def make_handler(songs: Songs, run_ffmpeg, token=None, jobs=None):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def end_headers(self):
            # La interfaz Tauri se sirve desde otro origen (tauri.localhost): permitir CORS.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Token, Range")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Expose-Headers", "Content-Range, Accept-Ranges, Content-Length")
            super().end_headers()

        def do_OPTIONS(self):
            self.send_response(204)
            self.end_headers()

        def _authorized(self, q):
            if not token:
                return True
            return self.headers.get("X-Token") == token or q.get("t", [""])[0] == token

        def _body(self):
            n = int(self.headers.get("Content-Length", "0") or 0)
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

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
            if parts and parts[0] in ("api", "media") and not self._authorized(q):
                return self.send_error(401)
            try:
                if parts[:2] == ["api", "jobs"] and jobs is not None:
                    return self._json(jobs.list())
                if parts[:2] == ["api", "settings"]:
                    from . import settings
                    return self._json(settings.load())
                if parts[:2] == ["api", "lists"]:
                    return self._json(library.load_lists())
                if parts[:2] == ["api", "version"]:
                    from . import paths
                    return self._json({"version": paths.app_version(), "bundled_models": paths.BUNDLED_MODELS})
                if parts[:2] == ["api", "diag"]:
                    from . import paths
                    f = paths.user_cache() / "registro.log"
                    return self._json({"path": str(f), "tail": f.read_text(encoding="utf-8", errors="replace")[-20000:] if f.exists() else ""})
                if parts[:2] == ["api", "models"]:
                    from . import downloads, paths
                    return self._json({"ready": paths.models_ready(), "dir": str(paths.MODELS_DIR),
                                       "download": downloads.MODELS.public()})
                if parts[:2] == ["api", "update"]:
                    from . import downloads
                    return self._json(downloads.UPDATE.public())
                if not parts:
                    return self._file(STATIC / "index.html")
                if len(parts) == 1 and re.fullmatch(r"[\w.-]+\.(css|js|html|png|svg|ico)", parts[0]):
                    return self._file(STATIC / parts[0])
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
                    if parts[1:] == ["pitchref"]:
                        pj = folder / "pitch.json"
                        if not pj.exists():
                            from .pitchref import compute
                            with _pitch_lock:
                                if not pj.exists():
                                    compute(folder / "voz.m4a", pj, run_ffmpeg)
                        return self._json(json.loads(pj.read_text(encoding="utf-8")))
                    if parts[1:] == ["pitch"]:
                        st = max(-12, min(12, int(q.get("st", ["0"])[0])))
                        if st == 0:
                            return self._json({"inst": "inst.m4a", "voz": "voz.m4a"})
                        with _render_lock:
                            return self._json(render_pitch(folder, st, run_ffmpeg))
                if parts[0] == "media" and len(parts) == 3:
                    folder = songs.folder(parts[1])
                    if folder is None:
                        return self.send_error(404)
                    if parts[2] == "video":
                        meta = json.loads((folder / library.SONG).read_text(encoding="utf-8"))
                        return self._file(Path(meta.get("video") or ""))
                    name = parts[2]
                    if not re.fullmatch(r"(inst|voz)(_[+-]\d+)?\.m4a|cover\.jpg", name):
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
            if not self._authorized(q):
                return self.send_error(401)
            try:
                return self._post(u, q)
            except Exception as e:
                return self._json({"error": str(e)}, 500)

        def _post(self, u, q):
            parts = [p for p in u.path.split("/") if p]
            if parts == ["api", "jobs"] and jobs is not None:
                body = self._body()
                from . import settings
                st = settings.load()
                out = []
                for item in body.get("inputs", []):
                    spec = {"input": item, "output_dir": st["output_dir"], "language": st["language"],
                            "quality": st["quality"], "guide_track": st["guide_track"],
                            "use_source_video": st["use_source_video"], "export_mp4": st.get("export_mp4", False),
                            "cookies_browser": st.get("cookies_browser", "")}
                    spec.update({k: v for k, v in body.get("options", {}).items()
                                 if k in ("semitones", "language", "lyrics", "artist", "title", "guide_track",
                                          "use_source_video", "quality", "export_mp4")})
                    out.append(jobs.add(spec).public())
                return self._json(out)
            if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "cancel" and jobs is not None:
                return self._json({"ok": jobs.cancel(parts[2])})
            if parts == ["api", "jobs", "clear"] and jobs is not None:
                jobs.clear_finished()
                return self._json({"ok": True})
            if parts == ["api", "settings"]:
                from . import settings
                return self._json(settings.save(self._body()))
            if parts == ["api", "lists"]:
                return self._json(library.save_lists(self._body()))
            if parts == ["api", "models", "download"]:
                from . import downloads
                url = self._body().get("url") or downloads.MODELS_URL
                if not (url.startswith("https://github.com/Rixmerz/Karaoke-easy/") or url.startswith("http://127.0.0.1:")):
                    return self._json({"error": "origen no permitido"}, 400)
                return self._json({"started": downloads.start_models(url)})
            if parts == ["api", "update", "download"]:
                from . import downloads
                return self._json({"started": downloads.start_update(self._body().get("url", ""))})
            if parts == ["api", "recording"]:
                folder = songs.folder(q.get("id", [""])[0])
                if folder is None:
                    return self._json({"error": "canción no encontrada"}, 404)
                n = int(self.headers.get("Content-Length", "0") or 0)
                if n <= 0 or n > 500 * 1024 * 1024:
                    return self._json({"error": "grabación vacía o demasiado grande"}, 400)
                import time as _t
                rec_dir = folder.parent / "grabaciones"
                rec_dir.mkdir(exist_ok=True)
                stamp = _t.strftime("%Y-%m-%d_%H-%M-%S")
                raw = rec_dir / f"grabacion_{stamp}.webm"
                with open(raw, "wb") as f:
                    left = n
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                mp3 = raw.with_suffix(".mp3")
                try:
                    run_ffmpeg(["-i", str(raw), "-c:a", "libmp3lame", "-b:a", "256k", str(mp3)])
                    raw.unlink()
                    out = mp3
                except Exception:
                    out = raw
                return self._json({"ok": True, "file": str(out), "folder": str(rec_dir)})
            if parts == ["api", "edit"]:
                folder = songs.folder(q.get("id", [""])[0])
                if folder is None:
                    return self._json({"error": "canción no encontrada"}, 404)
                b = self._body()
                library.edit_meta(folder, (b.get("title") or "").strip() or None, (b.get("artist") or "").strip())
                return self._json({"ok": True})
            if parts == ["api", "delete"]:
                folder = songs.folder(q.get("id", [""])[0])
                if folder is None:
                    return self._json({"error": "canción no encontrada"}, 404)
                library.unregister(folder)
                return self._json({"ok": True})
            if parts == ["api", "lyrics_search"]:
                from . import lyrics
                b = self._body()
                res = lyrics.search_all(b.get("artist", ""), b.get("title", ""))
                return self._json([{"artist": r.get("artistName"), "title": r.get("trackName"),
                                    "album": r.get("albumName"), "duration": r.get("duration"),
                                    "synced": bool(r.get("syncedLyrics")),
                                    "text": r.get("syncedLyrics") or r.get("plainLyrics")} for r in res[:15]])
            if u.path == "/api/save":
                folder = songs.folder(q.get("id", [""])[0])
                if folder is None:
                    return self._json({"error": "canción no encontrada"}, 404)
                library.save_lines(folder, self._body()["lines"])
                return self._json({"ok": True})
            self.send_error(404)

    return H


def start(extra_dirs=(), run_ffmpeg=None, port=0, token=None, jobs=None):
    if run_ffmpeg is None:
        from .pipeline import run_ffmpeg
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(Songs(extra_dirs), run_ffmpeg, token, jobs))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"
