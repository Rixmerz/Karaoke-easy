"""Alineación forzada palabra a palabra con MMS_FA (wav2vec2 multilingüe de Meta, vía torchaudio).

Dado el texto conocido de cada verso y una ventana aproximada de tiempo, calcula el instante exacto
de cada palabra sobre la pista de voz separada (CTC + Viterbi). Es la técnica usada para
sincronizar letras de karaoke; Whisper solo se usa para estimar las ventanas.
"""
import re
import unicodedata

import numpy as np

from . import paths
from .subtitles import Word

SR = 16000
FRAME = 0.02  # 20 ms por frame de wav2vec2
_MODEL = None


def model_file():
    return paths.MODELS_DIR / "mms_fa_fp16.pt"


def load_model(device="cpu"):
    global _MODEL
    if _MODEL is None:
        import torch
        from torchaudio.pipelines import MMS_FA

        if model_file().exists():
            from torchaudio.models import wav2vec2_model

            model = wav2vec2_model(**MMS_FA._params)
            state = torch.load(model_file(), map_location="cpu")
            model.load_state_dict({k.removeprefix("model."): v.float() for k, v in state.items()})
        else:  # desarrollo: descarga normal
            model = MMS_FA.get_model(with_star=False).model
        _MODEL = (model.to(device).eval(), MMS_FA.get_dict(star=None), device)
    return _MODEL


def romanize(word: str) -> str:
    w = unicodedata.normalize("NFKD", word.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z']", "", w)


def emissions(audio: np.ndarray, device="cpu", chunk=20.0, ctx=1.0):
    """Log-probabilidades CTC por frame, calculadas por trozos (canciones largas sin agotar memoria)."""
    import torch

    model, _, device = load_model(device)
    n, step, pad = len(audio), int(chunk * SR), int(ctx * SR)
    out = []
    with torch.inference_mode():
        for s in range(0, n, step):
            a, b = max(0, s - pad), min(n, s + step + pad)
            x = torch.from_numpy(audio[a:b].astype(np.float32))[None].to(device)
            x = torch.nn.functional.layer_norm(x, x.shape)  # normalización que espera MMS_FA
            em, _ = model(x)
            em = torch.log_softmax(em, -1)[0].cpu().numpy()
            f0 = int(round((s - a) / SR / FRAME))
            f1 = f0 + int(round((min(n, s + step) - s) / SR / FRAME))
            out.append(em[f0:f1])
    return np.concatenate(out) if out else np.zeros((0, 29), np.float32)


def ctc_align(em: np.ndarray, tokens):
    """Viterbi CTC. em: (T, C) log-probs; tokens: ids (sin blank=0). Devuelve (frame por token, score medio)."""
    T, L = len(em), len(tokens)
    S = 2 * L + 1
    if L == 0 or T < L:
        return None, -np.inf
    ext = np.zeros(S, dtype=np.int64)
    ext[1::2] = tokens
    allow_skip = np.zeros(S, dtype=bool)
    for s in range(3, S, 2):
        allow_skip[s] = ext[s] != ext[s - 2]
    NEG = -1e30
    dp = np.full(S, NEG)
    dp[0], dp[1] = em[0, 0], em[0, ext[1]]
    bp = np.zeros((T, S), dtype=np.int8)
    for t in range(1, T):
        stay = dp
        prev1 = np.concatenate(([NEG], dp[:-1]))
        prev2 = np.where(allow_skip, np.concatenate(([NEG, NEG], dp[:-2])), NEG)
        stack = np.stack([stay, prev1, prev2])
        arg = stack.argmax(0)
        dp = stack[arg, np.arange(S)] + em[t, ext]
        bp[t] = arg
    s = S - 1 if dp[S - 1] >= dp[S - 2] else S - 2
    best = dp[s]
    path = np.empty(T, dtype=np.int64)
    for t in range(T - 1, -1, -1):
        path[t] = s
        s -= bp[t, s]
    # primer y último frame de cada token
    first, last = np.full(L, -1), np.full(L, -1)
    for t, st in enumerate(path):
        if st % 2 == 1:
            k = st // 2
            if first[k] < 0:
                first[k] = t
            last[k] = t
    return (first, last), best / T


def voiced_mask(audio: np.ndarray, rel_db=30.0):
    """Frames de 20 ms con voz (energía de la pista de voz separada)."""
    hop = int(SR * FRAME)
    n = len(audio) // hop
    fr = audio[: n * hop].reshape(n, hop)
    db = 10 * np.log10((fr ** 2).mean(1) + 1e-12)
    return db > db.max() - rel_db


def silence_bias(em: np.ndarray, voiced: np.ndarray, pad=0.15, penalty=8.0):
    """Penaliza letras en frames sin voz (dilatados `pad` s): el Viterbi deja las pausas e
    interludios instrumentales como blank y no estira ni coloca palabras sobre ellos."""
    n = min(len(em), len(voiced))
    k = max(1, int(pad / FRAME))
    v = np.convolve(voiced[:n].astype(np.float32), np.ones(2 * k + 1), "same") > 0
    out = em.copy()
    out[:n][~v, 1:] -= penalty
    return out


def start_to_voice(s, e, voiced, max_shift=0.3):
    """Adelanta el inicio de la palabra al primer frame con voz (si cayó en silencio)."""
    a, b = int(s / FRAME), min(len(voiced), int(e / FRAME), int((s + max_shift) / FRAME))
    for f in range(a, b):
        if voiced[f]:
            return max(s, f * FRAME)
    return s


def trim_to_voice(s, e, voiced, max_gap=0.35):
    """Corta el final de la palabra cuando la voz se apaga (evita palabras estiradas sobre silencios)."""
    a, b = int(s / FRAME), min(len(voiced), int(e / FRAME))
    if b <= a + 1:
        return e
    gap, last_v = 0, None
    for f in range(a, b):
        if voiced[f]:
            last_v, gap = f, 0
        else:
            gap += 1
            if last_v is not None and gap * FRAME > max_gap:
                break
    if last_v is None:
        return min(e, s + 0.4)
    return max(s + 0.08, (last_v + 1) * FRAME)


def align_lines(vocals_16k: np.ndarray, line_words, windows, device="cpu", log=print, min_score=-4.5):
    """line_words: [[Word,...] por verso] con tiempos aproximados (se respetan textos y saltos).
    windows: [(t0, t1)] ventana de búsqueda por verso. Devuelve la lista de Word refinada."""
    _, vocab, _ = load_model(device)
    em_all = emissions(vocals_16k, device)
    voiced = voiced_mask(vocals_16k)
    em_all = silence_bias(em_all, voiced)
    out, refined, prev_end = [], 0, 0.0
    for words, (w0, w1) in zip(line_words, windows):
        w0 = max(w0, prev_end - 0.05, 0.0)
        f0, f1 = int(w0 / FRAME), min(len(em_all), int(w1 / FRAME))
        toks, spans = [], []
        for w in words:
            r = [vocab[c] for c in romanize(w.text) if c in vocab]
            spans.append((len(toks), len(toks) + len(r)))
            toks += r
        res, score = ctc_align(em_all[f0:f1], toks) if f1 - f0 > len(toks) else (None, -np.inf)
        if res is None or score < min_score:
            out += words
            if words:
                prev_end = words[-1].end
            continue
        first, last = res
        new = []
        for w, (a, b) in zip(words, spans):
            if b > a:
                s = w0 + first[a] * FRAME
                e = w0 + (last[b - 1] + 1) * FRAME
                e = trim_to_voice(s, e, voiced)
                s = min(start_to_voice(s, e, voiced), e - 0.05)
                new.append(Word(w.text, s, e))
            else:  # palabra sin letras alineables (números, símbolos): se completa luego
                new.append(Word(w.text, None, None))
        for i, w in enumerate(new):
            if w.start is None:
                p = new[i - 1].end if i else w0
                w.start = w.end = p
        out += new
        prev_end = new[-1].end
        refined += 1
    align_lines.last_refined = refined
    log(f"Alineación forzada (MMS_FA): {refined}/{len(line_words)} versos refinados.")
    return out
