import json
import zipfile

import pytest

from karaoke_easy import library, paths


@pytest.fixture
def cache(tmp_path, monkeypatch):
    c = tmp_path / "cache"
    c.mkdir()
    monkeypatch.setattr(paths, "user_cache", lambda: c)
    return c


def _song(root, title, artist, video=None):
    f = root / f"{title}_karaoke" / library.PKG
    f.mkdir(parents=True)
    (f / "inst.m4a").write_bytes(b"inst-" + title.encode())
    (f / "voz.m4a").write_bytes(b"voz")
    (f / "inst_+2.m4a").write_bytes(b"transpuesta")  # no debe exportarse
    (f / "pitch.json").write_text("{}")
    meta = {"title": title, "artist": artist, "lines": [[{"w": "hola", "s": 1.0, "e": 1.5}]], "video": video}
    (f / library.SONG).write_text(json.dumps(meta), encoding="utf-8")
    return f


def test_roundtrip_varias_canciones_con_video(tmp_path, cache):
    vid = tmp_path / "orig.mp4"
    vid.write_bytes(b"video")
    a = _song(tmp_path, "Uno", "Artista", str(vid))
    b = _song(tmp_path, "Dos", "Artista")
    pkg = library.export_songs([a, b], tmp_path / "out" / "mis")
    assert pkg.suffix == ".karaoke"
    names = zipfile.ZipFile(pkg).namelist()
    assert "Artista - Uno/video.mp4" in names and not any("inst_+2" in n for n in names)
    out = library.import_package(pkg, tmp_path / "imp")
    assert len(out) == 2
    m = json.loads((out[0] / library.SONG).read_text(encoding="utf-8"))
    assert m["title"] == "Uno" and m["lines"][0][0]["w"] == "hola"
    assert open(m["video"], "rb").read() == b"video"
    ids = {s["folder"] for s in library.list_songs()}
    assert {str(o.resolve()) for o in out} <= ids
    # importar otra vez no pisa: crea "(2)"
    again = library.import_package(pkg, tmp_path / "imp")
    assert all("(2)" in str(x) for x in again)


def test_rechaza_rutas_peligrosas_y_zip_ajeno(tmp_path, cache):
    bad = tmp_path / "bad.karaoke"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../../evil/cancion.json", "{}")
        z.writestr("x/../../inst.m4a", "x")
        z.writestr("otra/cosa.txt", "x")
    with pytest.raises(ValueError):
        library.import_package(bad, tmp_path / "imp")
    assert not (tmp_path / "evil").exists()
