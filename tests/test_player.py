import json
import urllib.request

import numpy as np
import soundfile as sf

from karaoke_easy import library, server
from karaoke_easy.pipeline import run_ffmpeg
from karaoke_easy.subtitles import Word


def make_song(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    folder = tmp_path / "Tema_karaoke" / library.PKG
    folder.mkdir(parents=True)
    (tmp_path / "Tema_karaoke" / "_trabajo").mkdir()
    sr = 22050
    wav = tmp_path / "a.wav"
    sf.write(wav, np.zeros((sr * 3, 2), np.float32), sr)
    for n in ("inst.m4a", "voz.m4a"):
        run_ffmpeg(["-i", str(wav), "-c:a", "aac", str(folder / n)])
    words = [Word("Hola", 1.0, 1.4), Word("mundo", 1.5, 2.0), Word("\nAdiós", 2.2, 2.8)]
    meta = {"title": "Tema", "artist": "Yo", "key": [9, True], "key_name": "Am", "duration": 3.0,
            "beats": [], "lines": library.words_to_lines(words), "video": None}
    (folder / library.SONG).write_text(json.dumps(meta), encoding="utf-8")
    library.register(folder)
    return folder


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, dict(r.headers), r.read()


def test_library_and_lines_roundtrip(tmp_path, monkeypatch):
    folder = make_song(tmp_path, monkeypatch)
    songs = library.list_songs()
    assert len(songs) == 1 and songs[0]["title"] == "Tema" and songs[0]["key"] == "Am"
    meta = json.loads((folder / library.SONG).read_text(encoding="utf-8"))
    assert [[w["w"] for w in l] for l in meta["lines"]] == [["Hola", "mundo"], ["Adiós"]]
    words = library.lines_to_words(meta["lines"])
    assert [w.text for w in words] == ["Hola", "mundo", "\nAdiós"]


def test_server_api_range_and_save(tmp_path, monkeypatch):
    folder = make_song(tmp_path, monkeypatch)
    httpd, url = server.start()
    try:
        sid = library.song_id(folder)
        st, _, body = get(url + "api/library")
        assert json.loads(body)[0]["id"] == sid
        st, _, body = get(url + f"api/song?id={sid}")
        assert json.loads(body)["title"] == "Tema"
        size = (folder / "inst.m4a").stat().st_size
        st, h, body = get(url + f"media/{sid}/inst.m4a", {"Range": "bytes=10-19"})
        assert st == 206 and len(body) == 10 and h["Content-Range"] == f"bytes 10-19/{size}"
        st, _, body = get(url)
        assert b"Karaoke Easy" in body
        # rutas no permitidas
        try:
            get(url + f"media/{sid}/..%2F..%2Fsecreto.txt")
            assert False
        except urllib.error.HTTPError as e:
            assert e.code in (403, 404)
        # guardar sincronía editada
        lines = json.loads(get(url + f"api/song?id={sid}")[2])["lines"]
        lines[1][0]["s"] += 0.5
        req = urllib.request.Request(url + f"api/save?id={sid}", data=json.dumps({"lines": lines}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
        saved = json.loads((folder / library.SONG).read_text(encoding="utf-8"))
        assert saved["lines"][1][0]["s"] == 2.7
        manual = json.loads((folder.parent / "_trabajo" / "letra_manual.json").read_text(encoding="utf-8"))
        assert manual[2]["text"] == "\nAdiós" and manual[2]["start"] == 2.7
    finally:
        httpd.shutdown()
