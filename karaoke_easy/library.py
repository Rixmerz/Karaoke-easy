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
    try:  # curva de notas para la puntuación
        from .pitchref import compute
        compute(voc, folder / "pitch.json")
    except Exception:
        pass
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


def load_lists():
    """Favoritos y listas de canciones (ids)."""
    try:
        d = json.loads((paths.user_cache() / "listas.json").read_text(encoding="utf-8"))
        return {"favorites": list(d.get("favorites", [])), "playlists": list(d.get("playlists", []))}
    except Exception:
        return {"favorites": [], "playlists": []}


def save_lists(d):
    clean = {"favorites": [str(x) for x in d.get("favorites", [])][:5000],
             "playlists": [{"id": str(p.get("id")), "name": str(p.get("name", ""))[:80],
                            "songs": [str(x) for x in p.get("songs", [])][:5000]}
                           for p in d.get("playlists", [])][:200]}
    (paths.user_cache() / "listas.json").write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    return clean


# ---------------- exportar / importar (.karaoke) ----------------
# Un .karaoke es un zip con una carpeta por canción: "<Artista - Título>/" con cancion.json, inst.m4a,
# voz.m4a, pitch.json, cover.jpg y (opcional) video.<ext>. Las versiones transpuestas no se incluyen
# (se regeneran). La app no comparte nada: solo guarda y abre sus propios archivos.
EXPORT_EXT = ".karaoke"
_PKG_FILES = ("cancion.json", "inst.m4a", "voz.m4a", "pitch.json", "cover.jpg")
_VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov")
_MAX_IMPORT = 4 * 1024 ** 3  # 4 GB descomprimido como máximo


def _safe_name(s: str) -> str:
    import re
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s or "").strip(" .")
    return s[:80] or "cancion"


def export_songs(folders, dest: Path, with_video=True) -> Path:
    import zipfile
    dest = Path(dest)
    if dest.suffix.lower() != EXPORT_EXT:
        dest = dest.with_suffix(EXPORT_EXT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    used = set()
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:  # audio y video ya vienen comprimidos
        for f in folders:
            f = Path(f)
            meta = json.loads((f / SONG).read_text(encoding="utf-8"))
            base = _safe_name(" - ".join(x for x in (meta.get("artist"), meta.get("title")) if x))
            name, i = base, 2
            while name.lower() in used:
                name, i = f"{base} ({i})", i + 1
            used.add(name.lower())
            for fn in _PKG_FILES:
                if fn != SONG and (f / fn).exists():
                    z.write(f / fn, f"{name}/{fn}")
            v = meta.get("video")
            if with_video and v and Path(v).exists() and Path(v).suffix.lower() in _VIDEO_EXT:
                vn = "video" + Path(v).suffix.lower()
                z.write(v, f"{name}/{vn}")
                meta["video"] = vn  # relativo dentro del paquete
            else:
                meta["video"] = None
            z.writestr(f"{name}/{SONG}", json.dumps(meta, ensure_ascii=False))
    tmp.replace(dest)
    return dest


def import_package(src: Path, dest_root: Path | None = None):
    """Importa un .karaoke (o .zip con el mismo formato). Devuelve las carpetas registradas."""
    import zipfile
    dest_root = Path(dest_root or paths.user_cache() / "importadas")
    out = []
    with zipfile.ZipFile(src) as z:
        infos = z.infolist()
        if sum(i.file_size for i in infos) > _MAX_IMPORT:
            raise ValueError("El archivo es demasiado grande.")
        songs = {}
        for i in infos:
            parts = i.filename.replace("\\", "/").split("/")
            if i.is_dir() or len(parts) != 2 or not parts[0] or parts[0] in (".", ".."):
                continue
            fn = parts[1]
            if fn in _PKG_FILES or (fn.startswith("video.") and Path(fn).suffix.lower() in _VIDEO_EXT):
                songs.setdefault(parts[0], {})[fn] = i
        songs = {k: v for k, v in songs.items() if SONG in v and "inst.m4a" in v}
        if not songs:
            raise ValueError("No es un archivo de canciones de Karaoke Easy.")
        for name, files in songs.items():
            meta = json.loads(z.read(files[SONG]).decode("utf-8"))
            base = dest_root / _safe_name(name)
            target, k = base, 2
            while target.exists():
                target, k = Path(f"{base} ({k})"), k + 1
            folder = target / PKG
            folder.mkdir(parents=True)
            for fn, info in files.items():
                if fn == SONG:
                    continue
                with z.open(info) as r, open(folder / fn, "wb") as w:
                    import shutil
                    shutil.copyfileobj(r, w, 1 << 20)
            vids = [fn for fn in files if fn.startswith("video.")]
            meta["video"] = str((folder / vids[0]).resolve()) if vids else None
            meta["imported"] = time.strftime("%Y-%m-%d %H:%M")
            (folder / SONG).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            register(folder)
            out.append(folder)
    return out
