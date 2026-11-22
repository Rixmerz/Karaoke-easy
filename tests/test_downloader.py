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
