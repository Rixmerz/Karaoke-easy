"""Curva de notas de referencia (de la voz separada) para la puntuación de afinación."""
import json
from pathlib import Path

import numpy as np

HOP = 0.05  # 20 valores por segundo


def compute(voz_audio: Path, out_json: Path, run_ffmpeg=None):
    import librosa
    import tempfile
    import os

    src = str(voz_audio)
    tmp = None
    if voz_audio.suffix.lower() != ".wav" and run_ffmpeg is not None:
        tmp = tempfile.TemporaryDirectory()
        src = os.path.join(tmp.name, "v.wav")
        run_ffmpeg(["-i", str(voz_audio), "-ac", "1", "-ar", "16000", src])
    y, sr = librosa.load(src, sr=16000, mono=True)
    hop = int(sr * HOP)
    f0 = librosa.yin(y, fmin=80, fmax=1000, sr=sr, frame_length=1024, hop_length=hop)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0][: len(f0)]
    db = 20 * np.log10(rms + 1e-9)
    voiced = db > (db.max() - 32)
    midi = 69 + 12 * np.log2(np.maximum(f0, 1e-6) / 440.0)
    # suavizar y quitar saltos aislados (mediana de 5)
    from scipy.signal import medfilt
    midi = medfilt(midi, 5)
    vals = [round(float(m), 1) if v and 36 <= m <= 90 else None for m, v in zip(midi, voiced)]
    out_json.write_text(json.dumps({"hop": HOP, "midi": vals}), encoding="utf-8")
    if tmp:
        tmp.cleanup()
    return out_json
