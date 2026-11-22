"""Ventana del reproductor (proceso aparte: pywebview necesita el hilo principal, igual que Tkinter)."""
import os
import subprocess
import sys
import time
import webbrowser


def launch(song_id: str | None = None, extra_dirs=()):
    """Abre el reproductor en un proceso nuevo (llamado desde la interfaz principal)."""
    args = ["--player"]
    if song_id:
        args += ["--song", song_id]
    for d in extra_dirs:
        args += ["--dir", str(d)]
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, *args]
    else:
        cmd = [sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run.py"), *args]
    flags = 0x08000000 if sys.platform == "win32" else 0
    subprocess.Popen(cmd, creationflags=flags)


def main(argv):
    from . import paths, server

    paths.setup_offline()
    song, dirs, selftest = None, [], "--selftest" in argv
    for i, a in enumerate(argv):
        if a == "--song" and i + 1 < len(argv):
            song = argv[i + 1]
        if a == "--dir" and i + 1 < len(argv):
            dirs.append(argv[i + 1])
    httpd, url = server.start(dirs)
    if song:
        url += f"?id={song}"
    try:
        import webview

        win = webview.create_window("Karaoke Easy — Reproductor", url, width=1280, height=760,
                                    min_size=(800, 500), background_color="#07070C")
        if selftest:
            def check(w):
                time.sleep(4)
                ok = w.evaluate_js("typeof openSong === 'function' && !!document.getElementById('lib')")
                print("PLAYER OK" if ok else "PLAYER FAIL", flush=True)
                w.destroy()
                os._exit(0 if ok else 1)
            webview.start(check, win)
        else:
            webview.start()
    except Exception as e:  # sin WebView2: usar el navegador predeterminado
        print("Reproductor en el navegador:", e, flush=True)
        if selftest:
            sys.exit(1)
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    httpd.shutdown()
