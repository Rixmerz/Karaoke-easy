# Versión Steam: cómo se construye

Mismo código que la versión directa. La edición se decide al construir (`karaoke_easy/edition.py`):

| | Directa (`direct`, por defecto) | Steam (`steam`) |
|---|---|---|
| Enlaces (YouTube, etc.) | Sí | No: la interfaz los oculta y `POST /api/jobs` los rechaza. Archivos locales e importar `.karaoke` sí |
| Licencia | Prueba 14 días + clave Lemon Squeezy | La da Steam (estado `steam`, todo lo personal). Solo la clave **Eventos** (uso comercial) se activa en Ajustes |
| Actualizaciones | Actualizador propio | Las entrega Steam: sin botón ni aviso; `/api/update*` no hacen nada |
| Steamworks | No | `cargo build --features steam` |
| yt-dlp / Deno en el motor | Incluidos | No se empaquetan |

Las reglas de cada plan están solo en `FEATURES` de `karaoke_easy/license.py`.

## Construir a mano (Windows)
1. `echo steam> EDITION` en la raíz (no se sube a git) y `pyinstaller --noconfirm KaraokeEasy.spec`.
2. `cargo build --release --features steam --manifest-path src-tauri/Cargo.toml`.
3. Carpeta final: `KaraokeEasy.exe`, `steam_api64.dll` y `engine\` (= `dist\KaraokeEngine`).
   La dll viene con el crate `steamworks-sys` (trae el SDK redistribuible); al compilar queda en
   `src-tauri\target\release\build\steamworks-sys-*\out\steam_api64.dll`.
4. Para probar sin pasar por Steam: poner `steam_appid.txt` (con el AppID) junto al exe y tener Steam abierto.

Para desarrollo sin construir: `KARAOKE_EDITION=steam` hace que el motor se comporte como la versión Steam.

## CI (`.github/workflows/windows-installer.yml`)
- Job `steam`: construye y publica el artefacto `KaraokeEasy-Steam-<versión>.zip`. No toca el instalador ni el Release de la versión directa.
- Job `steam-upload`: sube a SteamPipe (rama **beta**) con `game-ci/steam-deploy@v3.3.0`. Solo corre si existen los secretos y variables de abajo.

## Pendiente del dueño (TODO)
- **AppID**: cambiar `STEAM_APP_ID = 480` (app de prueba de Valve) en `src-tauri/src/steam.rs`.
- **Variables del repositorio** (Settings > Secrets and variables > Actions > Variables): `STEAM_APP_ID` y `STEAM_DEPOT_ID` (depot de Windows, normalmente AppID + 1).
- **Secretos**: `STEAM_USERNAME` (cuenta de compilación con permiso para subir builds, sin Steam Guard móvil) y `STEAM_CONFIG_VDF` (el `config.vdf` en base64 tras iniciar sesión una vez con `steamcmd`; ver la guía de game-ci/steam-deploy).
- En Steamworks: crear la rama `beta`, configurar la opción de inicio (`KaraokeEasy.exe`) y definir los logros (nombres de API para `steam_unlock_achievement`).
- Precio y producto de Eventos en Lemon Squeezy siguen como en `license.py` (TODOs ahí).
