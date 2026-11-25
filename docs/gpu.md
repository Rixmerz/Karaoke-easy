# Motor GPU (NVIDIA): complemento opcional

La app base procesa siempre con el procesador (motor CPU, `engine\KaraokeEngine.exe`, torch CPU)
y funciona en cualquier PC. El **Motor GPU** es un add-on que acelera los tres pasos pesados con CUDA:

| Paso (canción de 6 min) | CPU de 4 núcleos (medido) | NVIDIA (objetivo, **no medido**) |
|---|---|---|
| Demucs (separar voz) | 173 s | ~8–15 s |
| faster-whisper (float16) | 36 s | ~4–8 s |
| MMS_FA (alineación) | 60 s | ~2–5 s |

## Arquitectura

- El Motor GPU (`KaraokeEngine-GPU.exe`) es un segundo build PyInstaller del **mismo código** con torch CUDA.
  Solo hace de *proceso de trabajo*: el motor CPU sigue siendo el servidor que lanza la app Tauri
  (sin cambios en Rust) y, por cada canción, ejecuta `KaraokeEngine-GPU.exe --worker spec.json`
  en vez de a sí mismo. No lleva modelos: usa los del motor CPU (`KARAOKE_MODELS`) ni interfaz.
- Ubicación (`karaoke_easy/gpu.py: engine_candidates()`), en orden:
  1. `KARAOKE_GPU_ENGINE` (desarrollo);
  2. `<app>\gpu\KaraokeEngine-GPU.exe` — **DLC de Steam** (y también vale en la directa si se copia ahí);
  3. `%LOCALAPPDATA%\KaraokeEasy\gpu\KaraokeEngine-GPU.exe` — **pack descargado** (versión directa; la
     carpeta de instalación es de solo lectura).

## Selección y fallback (`karaoke_easy/gpu.py`, `jobs.py`)

Al arrancar, el motor CPU detecta en segundo plano:
1. **Tarjeta NVIDIA**: `nvidia-smi --query-gpu=name,driver_version,memory.total` (viene con el driver);
   si no está, WMI `Win32_VideoController` vía PowerShell (la versión de Windows `32.0.15.6094` se
   convierte a la NVIDIA `560.94`). Sin dependencias nuevas.
2. **Driver** ≥ 528.33 (mínimo de CUDA 12.x en Windows con compatibilidad de versión menor).
3. **Motor GPU instalado** y su **autoprueba** `--gpu-selftest`: importa torch y ctranslate2, comprueba
   `torch.cuda.is_available()`, hace una multiplicación en la GPU (detecta "no kernel image" si la
   arquitectura no está en el wheel), `ctranslate2.get_cuda_device_count()` y soporte float16.
   También compara la versión del Motor GPU con la de la app (el protocolo de trabajo debe coincidir).
4. Ajuste **"Usar la tarjeta gráfica"** (`use_gpu`, activado por defecto).

Si todo pasa, cada canción va a la GPU (`device="cuda"`). Si no, al procesador, y el motivo se ve en
Ajustes ("Usando: GPU (NVIDIA GeForce RTX …)" / "Usando: procesador — <motivo>") y en el registro
del trabajo. El último estado se guarda en `%LOCALAPPDATA%\KaraokeEasy\gpu_estado.json`.

**Fallo a mitad de trabajo** (CUDA sin memoria, driver que se cae, el proceso muere): si falló en
separar/letra/sincronizar (o murió sin avisar), la canción se repite automáticamente con el
procesador. Errores de la entrada (archivo inexistente, enlace) no se repiten. Tras 2 fallos seguidos
en GPU se usa el procesador hasta reiniciar la app.

## Build (CI: job `gpu` en `.github/workflows/windows-installer.yml`)

```
pip install torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt "ctranslate2>=4.5,<5" pyinstaller
set KARAOKE_GPU=1 && pyinstaller --noconfirm KaraokeEasy.spec   ->  dist\KaraokeEngine-GPU\
```

**Por qué cu128 + torch 2.7.1**: CUDA 12.8 es la primera que trae Blackwell (RTX 50xx, sm_120), y el
build cu128 de torch 2.7 compila además Maxwell→Ada/Hopper (sm_50…sm_90), es decir de la GTX 900 a la
RTX 50. cu126 no soporta las RTX 50 (las tarjetas que más se compran hoy); versiones posteriores de
torch quitan arquitecturas antiguas (Maxwell/Pascal) de sus builds CUDA 12.8+. El CI imprime las
arquitecturas del wheel y falla si falta sm_120 (avisa si falta sm_61). Driver: CUDA 12.x funciona
desde R525 (528.33 en Windows); las RTX 50 traen de fábrica drivers 570+.

**cuBLAS/cuDNN para faster-whisper**: ctranslate2 ≥ 4.5 en Windows se compila contra CUDA 12 + cuDNN 9
y carga `cublas64_12.dll`, `cublasLt64_12.dll` y `cudnn64_9.dll` por nombre. El wheel de torch cu128
ya trae esas DLL en `torch\lib` (cuBLAS 12.8, cuDNN 9.x, ABI compatible dentro de la versión mayor), así
que **no** se añaden los wheels `nvidia-cublas-cu12`/`nvidia-cudnn-cu12` (serían ~1 GB duplicado). El
Motor GPU, antes de trabajar, añade `torch\lib` a `PATH`/`os.add_dll_directory` e importa torch primero
(`gpu.prepare_dlls()`), así ctranslate2 encuentra las DLL ya cargadas. El CI verifica que esas DLL
estén dentro de `dist\KaraokeEngine-GPU\_internal\torch\lib`. Si en una GPU real ctranslate2 no las
encontrara, plan B: `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*` y añadir sus `bin\` en la spec.

**Tamaño esperado (estimado, no medido)**: wheel torch cu128 ≈ 3,3 GB; `dist\KaraokeEngine-GPU` ≈ 4–4,5 GB
sin comprimir (torch_cuda + cuDNN + cuBLAS son la mayor parte); zip (deflate rápido) ≈ 2,6–3,2 GB →
**2 partes** de ≤1900 MB. El CI imprime los tamaños reales. Tiempo de build: ~25–40 min (sin caché de pip
a propósito: el wheel de 3 GB desalojaría la caché de modelos del repositorio, límite 10 GB).

## Distribución

### Versión directa: pack dividido
Release `v<ver>` lleva:
- `KaraokeEasy-GPU-<ver>.zip.001`, `.002`, … — cortes binarios (7z `-v1900m`) de **un** zip cuyo
  contenido es `KaraokeEngine-GPU.exe` + `_internal\`;
- `KaraokeEasy-GPU-<ver>.json` — `{"version", "sha256", "size", "parts": [{"name","size","sha256"}]}`
  (`tools/gpu_manifest.py`).

En Ajustes, la fila **"Usar la tarjeta gráfica"** aparece solo si hay una NVIDIA (o el motor ya está
instalado). El botón *Descargar Motor GPU* (`POST /api/gpu/download`, `downloads.start_gpu`) baja el
manifiesto de la misma versión que la app, cada parte (verifica su sha256; las ya bajadas y válidas no
se repiten), las une, verifica el sha256 total, extrae (rechaza rutas `..`) en
`%LOCALAPPDATA%\KaraokeEasy\gpu` y vuelve a hacer la autoprueba. Tras actualizar la app, el Motor GPU
viejo queda desactivado ("otra versión") y el botón pasa a *Actualizar Motor GPU*.

### Steam: DLC gratuito "Motor GPU"
Depot opcional que se instala en `<app>\gpu\`. Ver `docs/steam-build.md`.

## API
- `GET /api/gpu` → `{nvidia, gpu, driver_ok, installed, enabled, checking, selftest, using: "gpu"|"cpu",
  device_name, reason, download, can_download}`
- `POST /api/gpu/download` (solo directa), `POST /api/gpu/recheck`.
- Cada trabajo expone `engine: "gpu"|"cpu"`.

## Qué está verificado y qué no
- Verificado (tests sin GPU, `tests/test_gpu.py`): parseo de nvidia-smi/WMI, versión de driver,
  decisión y motivos, fallback a CPU al fallar en GPU, partes + sha256 + reensamblado + instalación.
- **No verificado** (no hay GPU en el entorno de desarrollo ni en el CI): que el build cu128 congelado
  ejecute CUDA, que ctranslate2 use las DLL de torch, los tiempos reales y el tamaño final. El CI solo
  comprueba que el Motor GPU arranca, carga sus librerías y responde a `--gpu-selftest` (con "sin CUDA").

## Pendiente del dueño
- Probar en al menos una GTX 10xx/16xx, una RTX 30/40 y una RTX 50: Ajustes debe decir "Usando: GPU" y
  el registro del trabajo "Usando la tarjeta gráfica"; medir tiempos.
- Si VRAM ≤ 4 GB da "out of memory" en Demucs, bajar `segment`/`split` en `pipeline.py` para CUDA.
- Steam: crear el DLC y su depot (ver `docs/steam-build.md`).
