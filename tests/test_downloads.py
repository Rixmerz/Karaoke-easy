import functools
import http.server
import threading
import time
import zipfile

from karaoke_easy import downloads, paths


def serve(folder):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(folder))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def wait(d, timeout=20):
    t0 = time.time()
    while d.state in ("running", "extracting") and time.time() - t0 < timeout:
        time.sleep(0.05)
    return d.state


def test_models_download_and_install(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(paths, "MODELS_DIR", tmp_path / "appdata" / "KaraokeEasy" / "models")
    srv = tmp_path / "srv"
    srv.mkdir()
    with zipfile.ZipFile(srv / "KaraokeEasy-Modelos.zip", "w") as z:
        z.writestr("models/demucs/htdemucs.yaml", "models: ['955717e8']\n")
        z.writestr("models/demucs/955717e8-8726e21a.th", b"x" * 1000)
        z.writestr("models/mms_fa_fp16.pt", b"y" * 1000)
        z.writestr("models/whisper-small/model.bin", b"z" * 1000)
    assert not paths.models_ready()
    httpd = serve(srv)
    try:
        d = downloads.Download()
        monkeypatch.setattr(downloads, "MODELS", d)
        downloads.start_models(f"http://127.0.0.1:{httpd.server_address[1]}/KaraokeEasy-Modelos.zip")
        assert wait(d) == "done", d.error
        assert d.progress == 1.0
        assert paths.models_ready()
        assert (paths.MODELS_DIR / "whisper-small" / "model.bin").exists()
    finally:
        httpd.shutdown()


def test_models_zip_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(paths, "MODELS_DIR", tmp_path / "appdata" / "KaraokeEasy" / "models")
    srv = tmp_path / "srv"
    srv.mkdir()
    with zipfile.ZipFile(srv / "m.zip", "w") as z:
        z.writestr("../../malo.txt", "x")
    httpd = serve(srv)
    try:
        d = downloads.Download()
        monkeypatch.setattr(downloads, "MODELS", d)
        downloads.start_models(f"http://127.0.0.1:{httpd.server_address[1]}/m.zip")
        assert wait(d) == "error"
        assert not (tmp_path / "malo.txt").exists()
    finally:
        httpd.shutdown()


def test_update_only_from_official_releases():
    import pytest
    with pytest.raises(ValueError):
        downloads.start_update("https://ejemplo.com/virus.exe")
    with pytest.raises(ValueError):
        downloads.start_update("https://github.com/Rixmerz/Karaoke-easy/releases/download/v2/notas.txt")
