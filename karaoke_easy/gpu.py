"""Motor GPU (NVIDIA): complemento opcional que acelera Demucs, Whisper y MMS_FA con CUDA.

La app base funciona siempre con el procesador (motor CPU, `engine\\KaraokeEngine.exe`).
El Motor GPU es un segundo motor PyInstaller (`KaraokeEngine-GPU.exe`, torch con CUDA) que
solo se usa como *proceso de trabajo*: el motor CPU sigue siendo el servidor y, para cada
canción, lanza `KaraokeEngine-GPU.exe --worker spec.json` en vez de a sí mismo.

Se usa la GPU solo si se cumplen las tres condiciones:
  1. el Motor GPU está instalado (ver `engine_candidates()`);
  2. hay una tarjeta NVIDIA con un driver suficientemente nuevo (`detect()`);
  3. la autoprueba `KaraokeEngine-GPU.exe --gpu-selftest` dice que CUDA funciona.
Si no, se usa el procesador y se recuerda el motivo (`status()["reason"]`). Ver docs/gpu.md.
"""
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

from . import paths

GPU_EXE = "KaraokeEngine-GPU.exe"
GPU_DIR = "gpu"  # carpeta relativa: <app>\gpu (DLC de Steam) o %LOCALAPPDATA%\KaraokeEasy\gpu (descarga)
# torch cu128 (CUDA 12.8). Con la compatibilidad de versión menor de CUDA 12 basta un driver
# R525+ en Windows (528.33); por debajo, CUDA ni arranca. La autoprueba es la verificación real.
MIN_DRIVER = (528, 33)
SELFTEST_TIMEOUT = 90
_NOWIN = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


# ---------------- detección de la tarjeta (sin dependencias nuevas) ----------------
def parse_nvidia_smi(out: str):
    """Salida de `nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits`."""
    gpus = []
    for line in (out or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2 or not parts[0] or not re.match(r"^\d+\.\d+", parts[1]):
            continue
        mem = None
        if len(parts) > 2:
            try:
                mem = int(float(parts[2]))
            except ValueError:
                pass
        gpus.append({"name": parts[0], "driver": parts[1], "memory_mb": mem})
    return gpus


def wmi_driver_to_nvidia(v: str):
    """Versión de Windows del driver NVIDIA -> versión NVIDIA. '32.0.15.6094' -> '560.94'
    (las últimas 5 cifras: 5 6 0 9 4)."""
    digits = re.sub(r"\D", "", (v or "").split(".", 2)[-1]) if v and v.count(".") >= 3 else ""
    if len(digits) < 5:
        return None
    d = digits[-5:]
    return f"{int(d[:3])}.{d[3:]}"


def parse_wmi(out: str):
    """Salida de PowerShell `Get-CimInstance Win32_VideoController | ConvertTo-Json` (objeto o lista)."""
    try:
        data = json.loads(out or "null")
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    gpus = []
    for d in data or []:
        name = (d.get("Name") or "").strip()
        if "nvidia" not in name.lower() and "nvidia" not in (d.get("AdapterCompatibility") or "").lower():
            continue
        ram = d.get("AdapterRAM")  # uint32 en WMI: tope 4 GB, solo orientativo
        gpus.append({"name": name, "driver": wmi_driver_to_nvidia(d.get("DriverVersion") or ""),
                     "memory_mb": int(ram) // 1048576 if isinstance(ram, (int, float)) and ram > 0 else None})
    return gpus


def driver_ok(ver) -> bool:
    m = re.match(r"^(\d+)\.(\d+)", ver or "")
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= MIN_DRIVER


def _run(cmd, timeout=10):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_NOWIN,
                           encoding="utf-8", errors="replace")
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""


def detect():
    """Tarjetas NVIDIA presentes: primero nvidia-smi (viene con el driver), luego WMI."""
    if os.environ.get("KARAOKE_FAKE_NVIDIA") is not None:  # pruebas: "Nombre,versión"
        return parse_nvidia_smi(os.environ["KARAOKE_FAKE_NVIDIA"])
    gpus = parse_nvidia_smi(_run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                                  "--format=csv,noheader,nounits"]))
    if not gpus and sys.platform == "win32":
        gpus = parse_wmi(_run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                               "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterCompatibility,"
                               "DriverVersion,AdapterRAM | ConvertTo-Json -Compress"], timeout=20))
    return gpus


# ---------------- dónde está instalado el Motor GPU ----------------
def app_root() -> Path:
    """Carpeta de la app (la que tiene KaraokeEasy.exe). El motor CPU está en <app>\\engine."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parent.parent


def engine_candidates():
    c = []
    if os.environ.get("KARAOKE_GPU_ENGINE"):
        c.append(Path(os.environ["KARAOKE_GPU_ENGINE"]))
    c.append(app_root() / GPU_DIR / GPU_EXE)             # Steam: DLC "Motor GPU" en <app>\gpu
    c.append(paths.user_cache() / GPU_DIR / GPU_EXE)     # directa: pack descargado
    return c


def find_engine():
    return next((p for p in engine_candidates() if p.is_file()), None)


# ---------------- autoprueba (se ejecuta DENTRO del Motor GPU) ----------------
def prepare_dlls():
    """ctranslate2 (faster-whisper) carga cuBLAS/cuDNN por nombre (cublas64_12.dll, cudnn64_9.dll).
    No se empaquetan aparte: se usan las que trae torch en torch\\lib. Se añaden a la búsqueda de
    DLL y se importa torch primero, así LoadLibrary encuentra las ya cargadas."""
    try:
        import torch
        lib = Path(torch.__file__).parent / "lib"
        if lib.is_dir():
            os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(lib))
    except Exception:
        pass


def selftest() -> dict:
    """Comprueba torch.cuda y ctranslate2 con CUDA. Devuelve un dict (se imprime como JSON)."""
    r = {"ok": False, "version": paths.app_version(), "device": None, "cuda": None, "error": None}
    try:
        prepare_dlls()
        import torch
        import ctranslate2  # antes de mirar CUDA: así un fallo al cargar sus DLL se ve aunque no haya GPU
        r["cuda"] = torch.version.cuda
        if not torch.cuda.is_available():
            r["error"] = "CUDA no está disponible (driver antiguo o tarjeta no compatible)"
            return r
        r["device"] = torch.cuda.get_device_name(0)
        cap = torch.cuda.get_device_capability(0)
        r["capability"] = f"{cap[0]}.{cap[1]}"
        x = torch.randn(256, 256, device="cuda")
        float((x @ x).sum().item())  # falla si la arquitectura no está en el wheel ("no kernel image")
        r["memory_mb"] = torch.cuda.get_device_properties(0).total_memory // 1048576
        if ctranslate2.get_cuda_device_count() < 1:
            r["error"] = "faster-whisper (ctranslate2) no ve la GPU"
            return r
        if "float16" not in ctranslate2.get_supported_compute_types("cuda"):
            r["error"] = "la GPU no admite float16 en ctranslate2"
            return r
        r["ok"] = True
    except Exception as e:
        r["error"] = f"{e.__class__.__name__}: {e}"[:400]
    return r


def selftest_main():
    print("GPU_SELFTEST " + json.dumps(selftest(), ensure_ascii=False), flush=True)


def parse_selftest(out: str):
    for line in (out or "").splitlines():
        if line.startswith("GPU_SELFTEST "):
            try:
                return json.loads(line[len("GPU_SELFTEST "):])
            except ValueError:
                break
    return None


def run_selftest(exe: Path) -> dict:
    try:
        p = subprocess.run([str(exe), "--gpu-selftest"], capture_output=True, text=True, timeout=SELFTEST_TIMEOUT,
                           stdin=subprocess.DEVNULL, creationflags=_NOWIN, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "la autoprueba del Motor GPU no respondió"}
    except Exception as e:
        return {"ok": False, "error": f"no se pudo ejecutar el Motor GPU: {e}"}
    return parse_selftest(p.stdout) or {"ok": False, "error": f"el Motor GPU no respondió a la autoprueba (código {p.returncode})"}


# ---------------- decisión ----------------
def decide(enabled, gpus, exe, test, app_version):
    """Lógica pura de selección (probada en tests). Devuelve (usar_gpu, motivo)."""
    if not gpus:
        return False, "No se detectó una tarjeta NVIDIA"
    g = gpus[0]
    if not driver_ok(g.get("driver")):
        return False, (f"El driver NVIDIA ({g.get('driver') or 'desconocido'}) es muy antiguo: "
                       f"actualízalo a {MIN_DRIVER[0]}.{MIN_DRIVER[1]} o más nuevo")
    if exe is None:
        return False, "El Motor GPU no está instalado"
    if not enabled:
        return False, "Desactivado en Ajustes"
    if test is None:
        return False, "Comprobando el Motor GPU…"
    if test.get("version") and app_version and test["version"] != app_version:
        return False, f"El Motor GPU es de otra versión ({test['version']}): actualízalo"
    if not test.get("ok"):
        return False, "La autoprueba del Motor GPU falló: " + (test.get("error") or "motivo desconocido")
    return True, None


class Selector:
    """Estado del motor GPU para esta sesión del motor CPU."""
    MAX_FAILS = 2  # fallos seguidos en GPU antes de dejarla para el resto de la sesión

    def __init__(self):
        self.lock = threading.Lock()
        self.gpus = None
        self.exe = None
        self.test = None
        self.fails = 0
        self.last_error = None
        self._probing = False

    def refresh(self, wait=False):
        """Vuelve a detectar (tras instalar el pack, por ejemplo). La autoprueba va en segundo plano."""
        with self.lock:
            if self._probing:
                return
            self._probing = True
            self.test = None

        def probe():
            try:
                self.gpus = detect()
                self.exe = find_engine()
                if self.gpus and self.exe and driver_ok(self.gpus[0].get("driver")):
                    self.test = run_selftest(self.exe)
                else:
                    self.test = {"ok": False, "skipped": True}
                _remember(self.public())
            finally:
                self._probing = False
        t = threading.Thread(target=probe, daemon=True)
        t.start()
        if wait:
            t.join()

    def _enabled(self):
        from . import settings
        return bool(settings.load().get("use_gpu", True))

    def choice(self):
        """(usar_gpu, motivo, exe)"""
        if self.gpus is None and not self._probing:
            self.refresh(wait=True)
        if self.fails >= self.MAX_FAILS:
            return False, f"La GPU falló en las últimas canciones ({self.last_error}); se usa el procesador hasta reiniciar", None
        test = None if self._probing else self.test
        use, why = decide(self._enabled(), self.gpus or [], self.exe, test, paths.app_version())
        return use, why, self.exe if use else None

    def job_result(self, ok, error=None):
        if ok:
            self.fails = 0
        else:
            self.fails += 1
            self.last_error = (error or "error")[:200]
        _remember(self.public())

    def public(self):
        use, why = decide(self._enabled(), self.gpus or [], self.exe, None if self._probing else self.test,
                          paths.app_version())
        if self.fails >= self.MAX_FAILS:
            use, why = False, f"La GPU falló en las últimas canciones ({self.last_error}); se usa el procesador hasta reiniciar"
        g = (self.gpus or [None])[0]
        name = (self.test or {}).get("device") or (g or {}).get("name")
        return {"nvidia": bool(self.gpus), "gpu": g, "driver_ok": bool(g and driver_ok(g.get("driver"))),
                "installed": self.exe is not None, "engine": str(self.exe) if self.exe else None,
                "enabled": self._enabled(), "checking": self._probing, "selftest": self.test,
                "using": "gpu" if use else "cpu", "device_name": name if use else None, "reason": why,
                "min_driver": f"{MIN_DRIVER[0]}.{MIN_DRIVER[1]}"}


def _remember(st):
    """Último estado en %LOCALAPPDATA%\\KaraokeEasy\\gpu_estado.json (para diagnóstico)."""
    try:
        (paths.user_cache() / "gpu_estado.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


SELECTOR = Selector()


def should_retry_on_cpu(state, step, cancelled=False):
    """¿Repetir en CPU un trabajo que falló en la GPU? Solo si falló en un paso que usa la GPU
    (o el proceso murió sin avisar), no si era un error de la entrada (archivo, enlace)."""
    if cancelled or state != "error":
        return False
    return step in (None, "separate", "lyrics", "sync")
