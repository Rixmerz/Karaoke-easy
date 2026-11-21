"""Pulso y compás: para que la cuenta atrás y las palabras 'cuadren' con los tiempos fuertes."""
from dataclasses import dataclass

import numpy as np

from .subtitles import Word


@dataclass
class Rhythm:
    tempo: float
    beats: np.ndarray      # segundos de cada tiempo (pulso)
    downbeats: np.ndarray  # tiempos fuertes (1 de cada compás)


def analyze(y: np.ndarray, sr: int, meter=4) -> Rhythm:
    import librosa

    env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, frames = librosa.beat.beat_track(onset_envelope=env, sr=sr, units="frames")
    beats = librosa.frames_to_time(frames, sr=sr)
    # Fase del compás: el tiempo fuerte suele concentrar más energía de graves/ataques
    strength = env[np.clip(frames, 0, len(env) - 1)] if len(frames) else np.array([])
    phase = int(np.argmax([strength[p::meter].mean() if len(strength[p::meter]) else 0 for p in range(meter)])) \
        if len(strength) >= meter else 0
    return Rhythm(float(np.atleast_1d(tempo)[0]), beats, beats[phase::meter])


def vocal_onsets(y: np.ndarray, sr: int) -> np.ndarray:
    import librosa

    return librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=True)


def grid(beats: np.ndarray, subdiv=4) -> np.ndarray:
    """Subdivisiones del pulso (por defecto semicorcheas)."""
    if len(beats) < 2:
        return beats
    pts = [b0 + (b1 - b0) * k / subdiv for b0, b1 in zip(beats, beats[1:]) for k in range(subdiv)]
    return np.array(pts + [beats[-1]])


def snap_words(words, onsets: np.ndarray, beat_grid: np.ndarray, tol_onset=0.08, tol_grid=0.05):
    """Ajusta el inicio de cada palabra al ataque de voz más cercano; si no hay, a la rejilla rítmica.
    Solo mueve si está muy cerca, y nunca altera el orden de las palabras."""
    out, moved = [], 0
    for i, w in enumerate(words):
        s = w.start
        cands = []
        if len(onsets):
            j = np.argmin(np.abs(onsets - s))
            if abs(onsets[j] - s) <= tol_onset:
                cands.append(onsets[j])
        if not cands and len(beat_grid):
            j = np.argmin(np.abs(beat_grid - s))
            if abs(beat_grid[j] - s) <= tol_grid:
                cands.append(beat_grid[j])
        if cands:
            lo = out[-1].start + 0.03 if out else 0.0
            hi = words[i + 1].start - 0.03 if i + 1 < len(words) else s + 1
            ns = float(min(max(cands[0], lo), hi, w.end - 0.03))
            if abs(ns - s) > 1e-3:
                moved += 1
            s = ns
        out.append(Word(w.text, s, max(w.end, s + 0.05)))
    for x, y in zip(out, out[1:]):
        if x.end > y.start:
            x.end = max(x.start + 0.05, y.start)
    return out, moved
