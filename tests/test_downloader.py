import functools
import http.server
import threading

import numpy as np
import soundfile as sf

from karaoke_easy.downloader import download, is_url


def test_is_url():
    assert is_url("https://www.youtube.com/watch?v=abc")
    assert is_url("www.youtube.com/watch?v=abc")
    assert not is_url(r"C:\Users\yo\Música\tema.mp3")
    assert not is_url("tema.mp3")


def test_download_generic_url(tmp_path):
    """yt-dlp de punta a punta con un servidor local (sin depender de YouTube)."""
    srv_dir = tmp_path / "srv"
    srv_dir.mkdir()
    sr = 22050
    sf.write(srv_dir / "Artista - Tema.wav", np.zeros((sr, 2), np.float32), sr)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(srv_dir))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/Artista%20-%20Tema.wav"
        path, artist, title = download(url, tmp_path / "out", want_video=False, log=lambda m: None)
    finally:
        httpd.shutdown()
    assert path.exists() and path.stat().st_size > 1000
    assert title == "Tema"


class _SlowHandler(http.server.BaseHTTPRequestHandler):
    data = b""
    hang_after = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        import time
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(self.data)))
        self.end_headers()
        sent = 0
        for i in range(0, len(self.data), 16384):
            if self.hang_after is not None and sent >= self.hang_after:
                time.sleep(30)
                return
            self.wfile.write(self.data[i:i + 16384])
            sent += 16384
            time.sleep(0.01)


def _serve_slow(data, hang_after=None):
    H = type("H", (_SlowHandler,), {"data": data, "hang_after": hang_after})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def test_download_reports_progress(tmp_path):
    import io
    buf = io.BytesIO()
    sf.write(buf, np.zeros((22050 * 6, 2), np.float32), 22050, format="WAV")
    httpd = _serve_slow(buf.getvalue())
    states = []
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/Artista%20-%20Tema.wav"
        path, _, _ = download(url, tmp_path, want_video=False, log=lambda m: None, status=states.append)
    finally:
        httpd.shutdown()
    fr = [s["fraction"] for s in states if s.get("phase") == "download" and s.get("fraction") is not None]
    assert path.exists() and len(fr) > 3 and fr[-1] == 1.0 and fr == sorted(fr)
    assert states[-1]["phase"] == "merge"


def test_download_stall_gives_clear_error(tmp_path):
    import pytest
    from karaoke_easy.downloader import Stalled
    import yt_dlp
    httpd = _serve_slow(b"\0" * 2_000_000, hang_after=200_000)
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/x.wav"
        with pytest.raises((Stalled, yt_dlp.utils.DownloadError)) as e:
            download(url, tmp_path, want_video=False, log=lambda m: None, stall_seconds=2)
        assert "no avanza" in str(e.value) or "timed out" in str(e.value).lower()
    finally:
        httpd.shutdown()


def test_is_url_accepts_paths():
    from pathlib import Path
    assert not is_url(Path("/tmp/tema.mp3"))
    assert not is_url(None)


def test_friendly_errors():
    from karaoke_easy.downloader import friendly_error
    assert "robot" in friendly_error("ERROR: [youtube] x: Sign in to confirm you’re not a bot. This helps")
    assert "no está disponible" in friendly_error("ERROR: [youtube] x: Video unavailable")
    assert friendly_error("ERROR: algo raro") == "algo raro"
