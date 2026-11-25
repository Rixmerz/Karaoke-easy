"""Descargas en segundo plano con progreso: actualizaciones y componentes (instalador ligero)."""
import json
import re
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


# ---------------- Motor GPU (NVIDIA), edición directa ----------------
# El pack se publica en el Release como un manifiesto + partes de <2 GB (límite de GitHub):
#   KaraokeEasy-GPU-<ver>.json  {"version", "sha256" (zip entero), "size", "parts": [{"name","size","sha256"}]}
#   KaraokeEasy-GPU-<ver>.zip.001, .002, …   (cortes binarios de un único .zip; ver docs/gpu.md)
RELEASES = "https://github.com/Rixmerz/Karaoke-easy/releases/download"
GPU = Download()


def gpu_manifest_url(version: str) -> str:
    return f"{RELEASES}/v{version}/KaraokeEasy-GPU-{version}.json"


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _fetch(url, dest: Path, on_bytes):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            on_bytes(len(chunk))


def check_manifest(m: dict, version=None):
    parts = m.get("parts") or []
    if not parts or not re.fullmatch(r"[0-9a-f]{64}", str(m.get("sha256", ""))):
        raise ValueError("manifiesto del Motor GPU no válido")
    for p in parts:
        if not re.fullmatch(r"KaraokeEasy-GPU-[\w.\-]+\.zip\.\d{3}", str(p.get("name", ""))) \
                or not re.fullmatch(r"[0-9a-f]{64}", str(p.get("sha256", ""))):
            raise ValueError("manifiesto del Motor GPU no válido")
    if version and m.get("version") and m["version"] != version:
        raise ValueError(f"el Motor GPU publicado es de otra versión ({m['version']})")
    return parts


def reassemble(part_files, out: Path, expected_sha256: str):
    """Une las partes en un .zip y comprueba su sha256."""
    with open(out, "wb") as f:
        for pf in part_files:
            with open(pf, "rb") as src:
                shutil.copyfileobj(src, f, 1 << 20)
    if _sha256(out) != expected_sha256:
        out.unlink(missing_ok=True)
        raise ValueError("el Motor GPU descargado está dañado (sha256 distinto); vuelve a intentarlo")
    return out


def install_gpu_zip(zip_path: Path, target: Path):
    from .gpu import GPU_EXE
    tmp = target.parent / (target.name + "_nuevo")
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        for m in z.namelist():
            if m.startswith("/") or ".." in Path(m).parts or ":" in m:
                raise ValueError("archivo del Motor GPU no válido")
        z.extractall(tmp)
    if not (tmp / GPU_EXE).is_file():
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("el pack no contiene " + GPU_EXE)
    shutil.rmtree(target, ignore_errors=True)
    tmp.replace(target)


def _gpu_job(d: Download, manifest_url: str, version):
    from . import gpu
    work = paths.user_cache() / "descarga_gpu"
    work.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(manifest_url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        m = json.loads(r.read().decode("utf-8"))
    parts = check_manifest(m, version)
    base = manifest_url.rsplit("/", 1)[0]
    total = sum(int(p.get("size") or 0) for p in parts) or 1
    got = 0

    def tick(n):
        nonlocal got
        got += n
        d.progress = min(0.99, got / total)
    files = []
    for p in parts:
        f = work / p["name"]
        if f.exists() and f.stat().st_size == int(p.get("size") or -1) and _sha256(f) == p["sha256"]:
            tick(f.stat().st_size)  # parte ya bajada en un intento anterior: se reanuda por partes
        else:
            part = f.with_name(f.name + ".part")
            _fetch(f"{base}/{p['name']}", part, tick)
            part.replace(f)
            if _sha256(f) != p["sha256"]:
                f.unlink(missing_ok=True)
                raise ValueError(f"la parte {p['name']} llegó dañada (sha256 distinto); vuelve a intentarlo")
        files.append(f)
    d.state = "extracting"
    z = reassemble(files, work / "KaraokeEasy-GPU.zip", m["sha256"])
    for f in files:
        f.unlink(missing_ok=True)
    install_gpu_zip(z, paths.user_cache() / gpu.GPU_DIR)
    shutil.rmtree(work, ignore_errors=True)
    gpu.SELECTOR.refresh()


def start_gpu(manifest_url=None, version=None):
    version = version or paths.app_version()
    url = manifest_url or gpu_manifest_url(version)
    with GPU.lock:
        if GPU.state in ("running", "extracting"):
            return False
        GPU.state, GPU.progress, GPU.error, GPU.path = "running", 0.0, None, None

    def run():
        try:
            _gpu_job(GPU, url, version)
            GPU.progress, GPU.state = 1.0, "done"
        except Exception as e:
            GPU.state, GPU.error = "error", str(e) or e.__class__.__name__
    threading.Thread(target=run, daemon=True).start()
    return True
