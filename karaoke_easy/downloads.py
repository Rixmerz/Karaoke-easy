"""Descargas en segundo plano con progreso: actualizaciones y componentes (instalador ligero)."""
import shutil
import threading
import urllib.request
import zipfile
from pathlib import Path

from . import paths

MODELS_URL = "https://github.com/Rixmerz/Karaoke-easy/releases/latest/download/KaraokeEasy-Modelos.zip"
UA = {"User-Agent": "KaraokeEasy"}


class Download:
    def __init__(self):
        self.state = "idle"  # idle | running | extracting | done | error
        self.progress = 0.0
        self.error = None
        self.path = None
        self.lock = threading.Lock()

    def public(self):
        return {"state": self.state, "progress": round(self.progress, 4), "error": self.error,
                "path": str(self.path) if self.path else None}

    def start(self, url, dest: Path, after=None):
        with self.lock:
            if self.state in ("running", "extracting"):
                return False
            self.state, self.progress, self.error, self.path = "running", 0.0, None, None
        threading.Thread(target=self._run, args=(url, Path(dest), after), daemon=True).start()
        return True

    def _run(self, url, dest, after):
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".part")
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        self.progress = got / total
            tmp.replace(dest)
            self.path = dest
            if after:
                self.state = "extracting"
                after(dest)
            self.progress, self.state = 1.0, "done"
        except Exception as e:
            self.state, self.error = "error", str(e) or e.__class__.__name__


UPDATE = Download()
MODELS = Download()


def start_update(url: str):
    if not url.startswith("https://github.com/Rixmerz/Karaoke-easy/releases/"):
        raise ValueError("origen de actualización no permitido")
    name = url.rsplit("/", 1)[-1]
    if not name.lower().endswith(".exe"):
        raise ValueError("la actualización debe ser un instalador .exe")
    return UPDATE.start(url, paths.user_cache() / "actualizacion" / name)


def _install_models(zip_path: Path):
    target = paths.MODELS_DIR
    tmp = target.parent / "models_nuevo"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        for m in z.namelist():  # sin rutas absolutas ni '..'
            if m.startswith("/") or ".." in Path(m).parts:
                raise ValueError("archivo de componentes no válido")
        z.extractall(tmp)
    inner = tmp / "models" if (tmp / "models").exists() else tmp
    shutil.rmtree(target, ignore_errors=True)
    inner.replace(target) if inner != tmp else tmp.replace(target)
    shutil.rmtree(tmp, ignore_errors=True)
    zip_path.unlink(missing_ok=True)
    if not paths.models_ready():
        raise RuntimeError("los componentes descargados están incompletos")


def start_models(url: str = MODELS_URL):
    return MODELS.start(url, paths.user_cache() / "componentes.zip", after=_install_models)
