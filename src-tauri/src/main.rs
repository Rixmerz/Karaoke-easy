// Karaoke Easy — app de escritorio (Tauri 2).
// Arranca el motor de procesamiento (KaraokeEngine.exe, sin ventana) y le pasa a la interfaz
// la dirección local y el token. Al cerrar la app, el motor se cierra.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent};

struct Engine {
    child: Mutex<Option<Child>>,
    info: Result<Info, String>,
}

#[derive(Clone, serde::Serialize)]
struct Info {
    url: String,
    token: String,
    selftest: bool,
}

#[tauri::command]
fn engine_info(state: tauri::State<'_, Engine>) -> Result<Info, String> {
    state.info.clone()
}

#[tauri::command]
fn selftest_done(app: tauri::AppHandle, ok: bool) {
    println!("UI SELFTEST {}", if ok { "OK" } else { "FAIL" });
    app.exit(if ok { 0 } else { 1 });
}

/// Ejecuta el instalador de una actualización (descargado por el motor) y cierra la app.
/// Solo acepta un .exe dentro de %LOCALAPPDATA%\KaraokeEasy\actualizacion.
#[tauri::command]
fn run_installer(app: tauri::AppHandle, path: String) -> Result<(), String> {
    let base = std::env::var("LOCALAPPDATA")
        .map(|b| PathBuf::from(b).join("KaraokeEasy").join("actualizacion"))
        .map_err(|_| "LOCALAPPDATA no definido".to_string())?;
    let p = PathBuf::from(&path).canonicalize().map_err(|e| e.to_string())?;
    let b = base.canonicalize().map_err(|e| e.to_string())?;
    let is_exe = p.extension().map(|e| e.eq_ignore_ascii_case("exe")).unwrap_or(false);
    if !p.starts_with(&b) || !is_exe {
        return Err("instalador no permitido".into());
    }
    Command::new(&p)
        .args(["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH"])
        .spawn()
        .map_err(|e| format!("no se pudo iniciar el instalador: {e}"))?;
    app.exit(0);
    Ok(())
}

/// Comando que lanza el motor: KARAOKE_ENGINE_CMD (desarrollo) o engine\KaraokeEngine.exe junto a la app.
fn engine_command() -> Result<Command, String> {
    if let Ok(cmdline) = std::env::var("KARAOKE_ENGINE_CMD") {
        let mut parts = cmdline.split_whitespace();
        let prog = parts.next().ok_or("KARAOKE_ENGINE_CMD vacío")?;
        let mut c = Command::new(prog);
        c.args(parts);
        return Ok(c);
    }
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let dir = exe.parent().map(PathBuf::from).unwrap_or_default();
    for cand in [dir.join("engine").join("KaraokeEngine.exe"), dir.join("engine").join("KaraokeEngine")] {
        if cand.exists() {
            return Ok(Command::new(cand));
        }
    }
    Err(format!("No se encontró el motor en {}", dir.join("engine").display()))
}

fn start_engine() -> Result<(Child, Info), String> {
    let mut cmd = engine_command()?;
    cmd.arg("--serve").stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: sin consola
    }
    let mut child = cmd.spawn().map_err(|e| format!("No se pudo iniciar el motor: {e}"))?;
    let stdout = child.stdout.take().ok_or("sin salida del motor")?;
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        let mut line = String::new();
        loop {
            line.clear();
            match reader.read_line(&mut line) {
                Ok(0) | Err(_) => {
                    let _ = tx.send(None);
                    return;
                }
                Ok(_) => {
                    if line.starts_with("ENGINE_READY") {
                        let _ = tx.send(Some(line.trim().to_string()));
                        // seguir vaciando la salida para que el motor nunca se bloquee
                        for _ in reader.lines() {}
                        return;
                    }
                }
            }
        }
    });
    let ready = match rx.recv_timeout(Duration::from_secs(120)) {
        Ok(Some(l)) => l,
        _ => {
            let _ = child.kill();
            return Err("El motor no respondió al iniciar.".into());
        }
    };
    let parts: Vec<&str> = ready.split_whitespace().collect();
    if parts.len() < 3 {
        return Err(format!("Respuesta inesperada del motor: {ready}"));
    }
    let token = if parts[2] == "-" { String::new() } else { parts[2].to_string() };
    let info = Info {
        url: format!("http://127.0.0.1:{}/", parts[1]),
        token,
        selftest: std::env::var("KARAOKE_UI_SELFTEST").is_ok(),
    };
    Ok((child, info))
}

fn main() {
    let (child, info) = match start_engine() {
        Ok((c, i)) => (Some(c), Ok(i)),
        Err(e) => (None, Err(e)),
    };
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .manage(Engine { child: Mutex::new(child), info })
        .invoke_handler(tauri::generate_handler![engine_info, selftest_done, run_installer])
        .build(tauri::generate_context!())
        .expect("error al iniciar Karaoke Easy");
    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(mut c) = handle.state::<Engine>().child.lock().unwrap().take() {
                drop(c.stdin.take()); // el motor detecta el cierre y termina
                std::thread::sleep(Duration::from_millis(300));
                let _ = c.kill();
            }
        }
    });
}
