//! Edición Steam: inicio del cliente de Steam y logros. Solo se compila con `--features steam`.
//!
//! Necesita `steam_api64.dll` junto a KaraokeEasy.exe. El crate `steamworks-sys` trae el SDK
//! redistribuible y copia la dll a `target/<perfil>/build/steamworks-sys-*/out/`; el CI la copia
//! desde ahí a la carpeta de la versión Steam (ver docs/steam-build.md).

use std::sync::Mutex;
use std::time::Duration;

use steamworks::{AppId, Client};

/// TODO(dueño): reemplazar 480 (Spacewar, la app de prueba de Valve) por el AppID real de Steamworks.
pub const STEAM_APP_ID: u32 = 480;

pub struct Steam {
    pub client: Mutex<Option<Client>>,
}

pub enum Init {
    /// Steam está relanzando la app a través del cliente: hay que salir ya.
    Relaunching,
    Ready(Client),
    Failed(String),
}

pub fn init() -> Init {
    // En desarrollo (con steam_appid.txt junto al exe) devuelve false y no relanza.
    if steamworks::restart_app_if_necessary(AppId(STEAM_APP_ID)) {
        return Init::Relaunching;
    }
    match Client::init_app(STEAM_APP_ID) {
        Ok(client) => {
            // Procesar los callbacks de Steam en segundo plano (logros, overlay...).
            let c = client.clone();
            std::thread::spawn(move || loop {
                c.run_callbacks();
                std::thread::sleep(Duration::from_millis(100));
            });
            Init::Ready(client)
        }
        Err(e) => Init::Failed(format!(
            "No se pudo conectar con Steam ({e}).\n\nAbre Steam, inicia sesión y vuelve a abrir Karaoke Easy desde tu biblioteca de Steam."
        )),
    }
}

/// Desbloquea un logro por su nombre de API (definido en Steamworks).
#[tauri::command]
pub fn steam_unlock_achievement(state: tauri::State<'_, Steam>, name: String) -> Result<(), String> {
    let guard = state.client.lock().map_err(|e| e.to_string())?;
    let client = guard.as_ref().ok_or("Steam no está disponible")?;
    let stats = client.user_stats();
    stats
        .achievement(&name)
        .set()
        .map_err(|_| format!("logro desconocido: {name}"))?;
    stats.store_stats().map_err(|_| "no se pudo guardar el logro en Steam".to_string())
}
