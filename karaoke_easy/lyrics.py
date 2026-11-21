"""Letra correcta desde LRCLIB (base de letras abierta, https://lrclib.net) y alineación con el audio.

Whisper da buenos *tiempos* pero a veces mal el *texto*. Aquí se toma el texto correcto
(de LRCLIB o pegado por el usuario) y se le asignan los tiempos de las palabras de Whisper
mediante alineación de secuencias; las palabras no reconocidas se interpolan.
"""
import difflib
import json
import re
import statistics
import unicodedata
import urllib.parse
import urllib.request

from .subtitles import Word

API = "https://lrclib.net/api/search"
UA = "KaraokeEasy/1.0 (https://github.com/rixmerz/karaoke-easy)"
LRC_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def guess_artist_title(filename: str):
    """'Soda Stereo - En la Ciudad de la Furia (Official Video)' -> (artista, título)."""
    name = re.sub(r"^[0-9a-f]{6,}-", "", filename)  # prefijos de subida
    name = name.replace("_", " ")
    name = re.sub(r"[\(\[].*?[\)\]]", "", name)
    name = re.sub(r"(?i)\b(official|video|audio|lyrics?|hd|4k|remaster(ed)?|vevo)\b.*$", "", name)
    name = re.sub(r"(?i)\s-\s*\w*vevo\s*$", "", name).strip(" -")
    if " - " in name:
        a, t = name.split(" - ", 1)
        return a.strip(), t.strip(" -")
    return "", name.strip()


def search(artist: str, title: str, duration: float | None = None, timeout=15):
    """Devuelve el mejor resultado de LRCLIB (dict) o None."""
    q = {"track_name": title}
    if artist:
        q["artist_name"] = artist
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        results = json.load(r)
    if not results and artist:
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode({"q": f"{artist} {title}"}),
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            results = json.load(r)
    results = [x for x in results if x.get("plainLyrics") or x.get("syncedLyrics")]
    if not results:
        return None

    def score(x):
        s = 0 if x.get("syncedLyrics") else 100
        if duration and x.get("duration"):
            s += abs(x["duration"] - duration) / 10
        return s
    return min(results, key=score)


def parse_lyrics(text: str):
    """Acepta LRC ([mm:ss.xx] línea) o texto plano. Devuelve [(tiempo|None, línea)]."""
    out = []
    for raw in text.splitlines():
        stamps = LRC_RE.findall(raw)
        line = LRC_RE.sub("", raw).strip()
        if not line:
            continue
        if stamps:
            for m, s in stamps:
                out.append((int(m) * 60 + float(s), line))
        else:
            out.append((None, line))
    if any(t is not None for t, _ in out):
        out.sort(key=lambda x: (x[0] is None, x[0] or 0))
    return out


def _norm(w: str) -> str:
    w = unicodedata.normalize("NFD", w.lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ]", "", w)


def align(lines, asr_words):
    """lines: [(t_lrc|None, texto)]; asr_words: [Word] de Whisper. Devuelve [Word] con el texto correcto.
    Cada línea nueva se marca con text que empieza por '\\n' para forzar el salto de línea."""
    ref = []  # (line_idx, texto)
    for i, (_, line) in enumerate(lines):
        for tok in line.split():
            ref.append((i, tok))
    if not ref:
        return []
    a = [_norm(t) for _, t in ref]
    b = [_norm(w.text) for w in asr_words]
    times = [None] * len(ref)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            w = asr_words[blk.b + k]
            times[blk.a + k] = (w.start, w.end)
    # Fuzzy dentro de los huecos 'replace' (p.ej. 'velar' ~ 'volar')
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            for i in range(i1, i2):
                best, bj = 0.0, None
                for j in range(j1, j2):
                    r = difflib.SequenceMatcher(None, a[i], b[j]).ratio()
                    if r > best:
                        best, bj = r, j
                if bj is not None and best >= 0.6:
                    times[i] = (asr_words[bj].start, asr_words[bj].end)

    # Desfase LRC -> audio por verso (las versiones de vídeo/álbum difieren por tramos):
    # se toma el de la línea anclada más cercana.
    line_off = {}
    prev = None
    for (li, _), t in zip(ref, times):
        if li != prev and t and lines[li][0] is not None:
            line_off[li] = t[0] - lines[li][0]
        prev = li
    if line_off:
        anchored = sorted(line_off)
        for li, (tl, line) in enumerate(lines):
            idx = [k for k, (l, _) in enumerate(ref) if l == li]
            if tl is None or any(times[k] for k in idx):
                continue
            near = min(anchored, key=lambda a: (abs(a - li), a > li))
            off = line_off[near]
            times[idx[0]] = (tl + off, tl + off + 0.3)

    # Monotonía: descartar anclas que retroceden en el tiempo
    last = -1.0
    for k, t in enumerate(times):
        if t:
            if t[0] < last:
                times[k] = None
            else:
                last = t[0]

    # Interpolar los huecos entre anclas, repartiendo por longitud de palabra
    anchors = [k for k, t in enumerate(times) if t]
    if not anchors:
        start = asr_words[0].start if asr_words else 1.0
        times[0] = (start, start + 0.3)
        anchors = [0]
    for k in range(anchors[0]):
        times[k] = (max(0, times[anchors[0]][0] - 0.35 * (anchors[0] - k)),) * 2
    for p, q in zip(anchors, anchors[1:] + [None]):
        if q is None:
            for k in range(p + 1, len(ref)):
                t0 = times[k - 1][1]
                times[k] = (t0, t0 + 0.35)
            continue
        if q - p <= 1:
            continue
        t0, t1 = times[p][1], times[q][0]
        span = ref[p + 1:q]
        tot = sum(len(t) + 1 for _, t in span)
        acc = t0
        for k, (_, t) in zip(range(p + 1, q), span):
            d = (t1 - t0) * (len(t) + 1) / tot
            times[k] = (acc, acc + d)
            acc += d

    out, prev_line = [], None
    for (li, tok), (s, e) in zip(ref, times):
        e = max(e, s + 0.05)
        text = ("\n" if li != prev_line and prev_line is not None else "") + tok
        out.append(Word(text, float(s), float(e)))
        prev_line = li
    # Ajustar finales para que no se solapen con la palabra siguiente
    for x, y in zip(out, out[1:]):
        if x.end > y.start:
            x.end = max(x.start + 0.05, y.start)
    return out


def initial_prompt(lines, max_chars=600):
    """Texto para orientar a Whisper con el vocabulario de la canción."""
    txt = " ".join(l for _, l in lines)
    return txt[:max_chars]


def split_lines(words):
    """Agrupa las palabras alineadas por verso (las que empiezan con '\\n' abren verso)."""
    lines = []
    for w in words:
        if w.text.startswith("\n") or not lines:
            lines.append([])
        lines[-1].append(w)
    return lines
