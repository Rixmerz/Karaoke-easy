"""Paquete de canción para el reproductor propio + biblioteca de canciones procesadas.

Cada canción procesada deja en <salida>/<nombre>_karaoke/reproductor/:
  cancion.json   título, artista, tono, tempo, pulsos, versos con tiempos por palabra
  inst.m4a       pista sin voz (tono original)
  voz.m4a        voz separada (tono original)
  inst_+2.m4a…   versiones transpuestas, generadas bajo demanda desde el reproductor
"""
import hashlib
import json
import time
from pathlib import Path

from . import paths
from .subtitles import Word, group_lines

PKG = "reproductor"
SONG = "cancion.json"


def _lib_file() -> Path:
    return paths.user_cache() / "biblioteca.json"


def _load_lib():
    try:
        return json.loads(_lib_file().read_text(encoding="utf-8"))
    except Exception:
        return []


def register(folder: Path):
    folder = str(Path(folder).resolve())
    hidden = paths.user_cache() / "ocultas.json"
    if folder in _hidden():
        hidden.write_text(json.dumps(sorted(_hidden() - {folder}), ensure_ascii=False), encoding="utf-8")
    lib = [p for p in _load_lib() if p != folder]
    lib.insert(0, folder)
    _lib_file().write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding="utf-8")


def song_id(folder) -> str:
    return hashlib.sha1(str(Path(folder).resolve()).encode("utf-8")).hexdigest()[:12]


def list_songs(extra_dirs=()):
    """Canciones disponibles (las registradas + las que haya en carpetas de salida conocidas)."""
    folders = list(_load_lib())
    for d in extra_dirs:
        for j in Path(d).glob(f"*_karaoke/{PKG}/{SONG}"):
            folders.append(str(j.parent.resolve()))
    seen, out = set(_hidden()), []
    for f in folders:
        j = Path(f) / SONG
        if f in seen or not j.exists():
            continue
        seen.add(f)
        try:
            meta = json.loads(j.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({"id": song_id(f), "folder": f, "title": meta.get("title"), "artist": meta.get("artist"),
                    "cover": (Path(f) / "cover.jpg").exists(), "video": meta.get("video"),
                    "key": meta.get("key_name"), "duration": meta.get("duration"), "created": meta.get("created")})
    return out


def words_to_lines(words):
    return [[{"w": w.text.lstrip("\n"), "s": round(w.start, 3), "e": round(w.end, 3)} for w in line]
            for line in group_lines(words)]


def lines_to_words(lines):
    out = []
    for line in lines:
        for i, w in enumerate(line):
            out.append(Word(("\n" if i == 0 and out else "") + w["w"], float(w["s"]), float(w["e"])))
    return out


def write_package(builder, words, inst: Path, voc: Path, run_ffmpeg):
    """Genera el paquete del reproductor a partir de un KaraokeBuilder ya ejecutado."""
    from . import music

    folder = builder.out / PKG
    folder.mkdir(parents=True, exist_ok=True)
    for src, name in ((inst, "inst.m4a"), (voc, "voz.m4a")):
        run_ffmpeg(["-i", str(src), "-c:a", "aac", "-b:a", "192k", str(folder / name)])
    import soundfile as sf

    dur = sf.info(str(inst)).duration
    r = builder.rhythm
    video = None
    if builder.src.suffix.lower() in {".mp4", ".mkv", ".mov", ".webm", ".avi"}:
        video = str(builder.src)
    tonic, minor = builder.key or (0, False)
    meta = {
        "version": 1,
        "title": builder.o.title_hint or builder.name,
        "artist": builder.o.artist_hint or "",
        "source": str(builder.src),
        "video": video,
        "duration": dur,
        "key": [tonic, minor],
        "key_name": music.key_name(tonic, minor),
        "tempo": r.tempo if r else None,
        "beats": [round(float(b), 3) for b in r.beats] if r else [],
        "lines": words_to_lines(words),
        "created": time.strftime("%Y-%m-%d %H:%M"),
    }
    if not meta["artist"]:
        from .lyrics import guess_artist_title
        a, t = guess_artist_title(builder.name)
        meta["artist"], meta["title"] = a, t or builder.name
    if video:  # portada para la biblioteca
        try:
            run_ffmpeg(["-ss", f"{dur * 0.3:.1f}", "-i", video, "-frames:v", "1", "-vf", "scale=480:-2",
                        "-q:v", "4", str(folder / "cover.jpg")])
            meta["cover"] = True
        except Exception:
            pass
    (folder / SONG).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    register(folder)
    return folder


def save_lines(folder: Path, lines):
    """Guarda la sincronía editada en el reproductor (y la deja para regenerar el vídeo)."""
    folder = Path(folder)
    j = folder / SONG
    meta = json.loads(j.read_text(encoding="utf-8"))
    meta["lines"] = lines
    j.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    work = folder.parent / "_trabajo"
    if work.exists():
        (work / "letra_manual.json").write_text(
            json.dumps([w.__dict__ for w in lines_to_words(lines)], ensure_ascii=False, indent=1), encoding="utf-8")


def unregister(folder: Path):
    folder = str(Path(folder).resolve())
    lib = [p for p in _load_lib() if p != folder]
    _lib_file().write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding="utf-8")
    hidden = paths.user_cache() / "ocultas.json"
    try:
        h = set(json.loads(hidden.read_text(encoding="utf-8")))
    except Exception:
        h = set()
    h.add(folder)
    hidden.write_text(json.dumps(sorted(h), ensure_ascii=False), encoding="utf-8")


def _hidden():
    try:
        return set(json.loads((paths.user_cache() / "ocultas.json").read_text(encoding="utf-8")))
    except Exception:
        return set()


def edit_meta(folder: Path, title=None, artist=None):
    j = Path(folder) / SONG
    meta = json.loads(j.read_text(encoding="utf-8"))
    if title:
        meta["title"] = title
    if artist is not None:
        meta["artist"] = artist
    j.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
