"""Cola de trabajos del motor: cada canción se procesa en un proceso aparte
(cancelar = terminarlo al instante; un fallo no tumba la aplicación)."""
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
                       make_video=spec.get("export_mp4", True),
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
        q.put(("done", {"video": str(video) if video else None, "mp3": str(mp3) if mp3 else None, "folder": str(b.out),
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
        while True:
            nxt = next((j for j in self.jobs if j.state == "queued"), None)
            if nxt is None:
                self.wake.wait(1.0)
                self.wake.clear()
                continue
            try:
                self._run(nxt)
            except Exception as e:  # nunca detener la cola
                nxt.state, nxt.error = "error", f"No se pudo iniciar el proceso: {e}"
                _diag(f"[{nxt.id}] no se pudo iniciar: {traceback.format_exc()}")

    @staticmethod
    def dl_update(j, val):
        if val is None:
            j.dl = None
            return
        val = dict(val)
        val["at"] = time.time()
        j.dl = val

    def _handle(self, j, kind, val):
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
        elif kind == "error":
            if j.state != "cancelled":
                j.state, j.error = "error", val

    def _run(self, j: Job):
        """Procesa la canción en un proceso aparte: el propio motor con --worker
        (sin multiprocessing: funciona igual con o sin consola, que es como lo lanza la app)."""
        import json
        import subprocess
        import sys
        from . import paths

        jobs_dir = paths.user_cache() / "trabajos"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        spec_file = jobs_dir / f"{j.id}.json"
        spec_file.write_text(json.dumps(j.spec, ensure_ascii=False), encoding="utf-8")
        err_file = jobs_dir / f"{j.id}.err.txt"
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--worker", str(spec_file)]
        else:
            cmd = [sys.executable, str(Path(__file__).resolve().parent.parent / "run.py"), "--worker", str(spec_file)]
        j.state, j.started = "running", time.time()
        _diag(f"[{j.id}] inicio: {j.spec.get('input')}")
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        with open(err_file, "w", encoding="utf-8", errors="replace") as err:
            j.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err,
                                      creationflags=flags, bufsize=1, text=True, encoding="utf-8", errors="replace")
            for line in j.proc.stdout:
                if not line.startswith(MARK):
                    continue  # salida de librerías: se ignora
                try:
                    kind, val = json.loads(line[len(MARK):])
                except Exception:
                    continue
                self._handle(j, kind, val)
                if kind in ("done", "error"):
                    break
            try:
                j.proc.wait(timeout=30)
            except Exception:
                _kill_tree(j.proc.pid)
        if j.state == "running":  # terminó sin avisar: mostrar el motivo
            tail = err_file.read_text(encoding="utf-8", errors="replace")[-1500:] if err_file.exists() else ""
            j.state = "error"
            j.error = "El proceso terminó inesperadamente."
            if tail.strip():
                j.log.append(tail)
                _diag(f"[{j.id}] stderr: {tail}")
        j.finished = time.time()
        _diag(f"[{j.id}] fin: estado={j.state} paso={j.step} error={j.error}")
        for f in (spec_file, err_file):
            try:
                f.unlink()
            except OSError:
                pass


MARK = "@@KE@@"


class _LineQueue:
    """Sustituye a multiprocessing.Queue: cada mensaje es una línea JSON marcada en stdout."""
    def __init__(self, out):
        import threading as _t
        self.out, self.lock = out, _t.Lock()

    def put(self, msg):
        import json
        with self.lock:
            self.out.write(MARK + json.dumps(list(msg), ensure_ascii=False) + "\n")
            self.out.flush()


def worker_main(spec_path):
    """Punto de entrada del proceso de trabajo (KaraokeEngine.exe --worker spec.json)."""
    import json
    import os
    import sys
    spec = json.loads(open(spec_path, encoding="utf-8").read())
    # stdout queda solo para los mensajes; lo que impriman las librerías va a stderr
    out = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr
    _worker(spec, _LineQueue(out))


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
            subprocess.run(["pkill", "-KILL", "-P", str(pid)], capture_output=True)  # hijos (ffmpeg…)
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
