"""Cola de trabajos del motor: cada canción se procesa en un proceso aparte
(cancelar = terminarlo al instante; un fallo no tumba la aplicación)."""
import multiprocessing as mp
import threading
import time
import traceback
import uuid
from pathlib import Path

STEPS = [  # clave, nombre visible, peso aproximado en el tiempo total
    ("prepare", "Preparando", 0.06),
    ("separate", "Separando pistas", 0.40),
    ("lyrics", "Letra", 0.18),
    ("sync", "Sincronizando", 0.10),
    ("video", "Video", 0.22),
    ("finish", "Listo", 0.04),
]
KEYS = [k for k, _, _ in STEPS]


def _worker(spec, q):
    """Se ejecuta en un proceso hijo."""
    try:
        q.put(("log", "Proceso de trabajo iniciado."))
        import sys
        from . import paths
        paths.setup_offline()
        if getattr(sys, "frozen", False) and not paths.models_ready():
            raise RuntimeError("Faltan los componentes de procesamiento. Descárgalos desde Ajustes › Componentes.")
        from .downloader import download, is_url
        from .pipeline import KaraokeBuilder, Options

        def log(m):
            q.put(("log", str(m)))

        q.put(("step", "prepare"))
        src, artist, title = spec["input"], spec.get("artist", ""), spec.get("title", "")
        out_dir = spec["output_dir"]
        if is_url(src):
            q.put(("dl", {"phase": "start"}))
            from .downloader import deno_path
            log(f"Descargando enlace (motor JavaScript: {'listo' if deno_path() else 'no encontrado'})…")
            from .downloader import friendly_error
            try:
                src, a, t = download(src, Path(out_dir) / "descargas", want_video=spec.get("use_source_video", True),
                                     log=log, progress=lambda p: q.put(("sub", p)), status=lambda d: q.put(("dl", d)),
                                     cookies_browser=spec.get("cookies_browser") or "")
            except Exception as e:
                log(traceback.format_exc())
                raise RuntimeError(friendly_error(str(e))) from None
            src = str(src)  # la descarga devuelve una ruta (Path); el resto del proceso usa texto
            q.put(("dl", None))
            artist, title = artist or a, title or t
            q.put(("meta", {"title": title, "artist": artist}))
        opts = Options(input_path=src, output_dir=out_dir, semitones=spec.get("semitones", 0),
                       whisper_model=spec.get("whisper_model", "small"), language=spec.get("language"),
                       use_source_video=spec.get("use_source_video", True), guide_track=spec.get("guide_track", True),
                       lyrics_text=spec.get("lyrics") or None, artist_hint=artist, title_hint=title)
        if spec.get("quality") == "720":
            opts.width, opts.height = 1280, 720
        b = KaraokeBuilder(opts, log=log, progress=lambda p: None, step=lambda k: q.put(("step", k)))
        video, mp3 = b.run()
        from .library import song_id
        if b.package:
            import json as _j
            m = _j.loads((b.package / "cancion.json").read_text(encoding="utf-8"))
            q.put(("meta", {"title": m.get("title"), "artist": m.get("artist")}))
        q.put(("done", {"video": str(video), "mp3": str(mp3), "folder": str(b.out),
                        "song_id": song_id(b.package) if b.package else None}))
    except Exception as e:
        q.put(("log", traceback.format_exc()))
        q.put(("error", str(e) or e.__class__.__name__))


class Job:
    def __init__(self, spec):
        self.id = uuid.uuid4().hex[:10]
        self.spec = spec
        src = spec["input"]
        self.title, self.artist = spec.get("title") or "", spec.get("artist") or ""
        if not self.title:
            if "://" in src or src.lower().startswith("www."):
                self.title = "Descargando…"
            else:
                from .lyrics import guess_artist_title
                a, t = guess_artist_title(Path(src).stem)
                self.title, self.artist = t or Path(src).stem, self.artist or a
        self.state = "queued"  # queued | running | done | error | cancelled
        self.step = None
        self.step_started = None
        self.sub = 0.0
        self.log = []
        self.result = None
        self.error = None
        self.created = time.time()
        self.started = None
        self.finished = None
        self.proc = None
        self.dl = None  # progreso de la descarga (enlaces)

    def fraction(self):
        if self.state == "done":
            return 1.0
        if self.step not in KEYS:
            return 0.0
        weights = [w for _, _, w in STEPS]
        if "://" in self.spec["input"] or self.spec["input"].lower().startswith("www."):
            weights[0] = 0.20  # descargar el enlace es una parte importante del tiempo
            tot = sum(weights)
            weights = [w / tot for w in weights]
        i = KEYS.index(self.step)
        done = sum(weights[:i])
        w = weights[i]
        # avance dentro del paso: sub-progreso real si hay, si no, estimación suave por tiempo
        inside = self.sub
        if not inside and self.step_started:
            inside = min(0.9, (time.time() - self.step_started) / (60 * w * 10))
        return min(0.99, done + w * inside)

    def eta(self):
        if self.state != "running" or not self.started:
            return None
        f = self.fraction()
        el = time.time() - self.started
        if f < 0.08 or el < 10:
            return None
        return max(0, el / f - el)

    def public(self):
        return {"id": self.id, "title": self.title, "artist": self.artist, "state": self.state,
                "step": self.step, "steps": [{"key": k, "name": n} for k, n, _ in STEPS],
                "fraction": round(self.fraction(), 4), "eta": self.eta(), "error": self.error,
                "result": self.result, "created": self.created, "log": self.log[-200:], "download": self.dl}


class JobManager:
    def __init__(self):
        self.jobs: list[Job] = []
        self.lock = threading.Lock()
        self.wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def add(self, spec) -> Job:
        j = Job(spec)
        with self.lock:
            self.jobs.append(j)
        self.wake.set()
        return j

    def get(self, jid):
        return next((j for j in self.jobs if j.id == jid), None)

    def cancel(self, jid):
        j = self.get(jid)
        if not j:
            return False
        if j.state == "queued":
            j.state = "cancelled"
        elif j.state == "running" and j.proc is not None:
            j.state = "cancelled"
            _kill_tree(j.proc.pid)
        return True

    def clear_finished(self):
        with self.lock:
            self.jobs = [j for j in self.jobs if j.state in ("queued", "running")]

    def list(self):
        return [j.public() for j in self.jobs]

    def _loop(self):
        ctx = mp.get_context("spawn")
        while True:
            nxt = next((j for j in self.jobs if j.state == "queued"), None)
            if nxt is None:
                self.wake.wait(1.0)
                self.wake.clear()
                continue
            self._run(nxt, ctx)

    @staticmethod
    def dl_update(j, val):
        if val is None:
            j.dl = None
            return
        val = dict(val)
        val["at"] = time.time()
        j.dl = val

    def _run(self, j: Job, ctx):
        q = ctx.Queue()
        j.state, j.started = "running", time.time()
        _diag(f"[{j.id}] inicio: {j.spec.get('input')}")
        j.proc = ctx.Process(target=_worker, args=(j.spec, q), daemon=True)
        j.proc.start()
        while True:
            try:
                kind, val = q.get(timeout=0.5)
            except Exception:
                if not j.proc.is_alive():
                    if j.state == "running":
                        j.state, j.error = "error", j.error or "El proceso terminó inesperadamente."
                    break
                continue
            if kind == "log":
                j.log.append(val)
                _diag(f"[{j.id}] {val}")
            elif kind == "step":
                if val != j.step:
                    _diag(f"[{j.id}] paso: {val}")
                    j.step, j.step_started, j.sub = val, time.time(), 0.0
            elif kind == "dl":
                self.dl_update(j, val)
            elif kind == "sub":
                j.sub = float(val)
            elif kind == "meta":
                j.title = val.get("title") or j.title
                j.artist = val.get("artist") or j.artist
            elif kind == "done":
                j.state, j.result, j.step = "done", val, "finish"
                break
            elif kind == "error":
                if j.state != "cancelled":
                    j.state, j.error = "error", val
                break
        j.finished = time.time()
        _diag(f"[{j.id}] fin: estado={j.state} paso={j.step} error={j.error}")
        j.proc.join(timeout=5)


def _diag(line):
    """Registro de diagnóstico en %LOCALAPPDATA%\\KaraokeEasy\\registro.log (máx. ~2 MB)."""
    try:
        from . import paths
        f = paths.user_cache() / "registro.log"
        if f.exists() and f.stat().st_size > 2_000_000:
            f.replace(f.with_suffix(".log.1"))
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(line).rstrip() + "\n")
    except Exception:
        pass


def _kill_tree(pid):
    """Termina el proceso y sus hijos (ffmpeg, etc.)."""
    import subprocess
    import sys
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                           creationflags=0x08000000)
        else:
            import os
            import signal
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
