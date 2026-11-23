"""Motor de Karaoke Easy: proceso sin ventana que lanza la app Tauri.

Arranca el servidor local con un token aleatorio y escribe en stdout:
    ENGINE_READY <puerto> <token>
Termina solo cuando la app se cierra (su stdin se cierra).
"""
import os
import secrets
import sys
import threading


def main(argv):
    from . import paths, server
    from .jobs import JobManager

    paths.setup_offline()
    port = 0
    token = secrets.token_urlsafe(24)
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    if "--no-token" in argv:  # solo desarrollo / pruebas en navegador
        token = None
    from .jobs import _diag
    _diag(f"motor iniciado (versión {paths.app_version()}, componentes en {paths.MODELS_DIR}, listos={paths.models_ready()})")
    jobs = JobManager()
    httpd, url = server.start(port=port, token=token, jobs=jobs)
    print(f"ENGINE_READY {httpd.server_address[1]} {token or '-'}", flush=True)

    def watch_parent():
        try:
            while sys.stdin.read(1):
                pass
        except Exception:
            pass
        os._exit(0)  # la app se cerró: terminar el motor y sus trabajos

    if "--no-stdin-watch" not in argv and sys.stdin is not None:
        threading.Thread(target=watch_parent, daemon=True).start()
    threading.Event().wait()
