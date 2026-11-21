"""Detección de tonalidad y transposición (notación americana)."""
import numpy as np

NOTES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
# Tonalidades que se escriben normalmente con bemoles
FLAT_MAJOR = {1, 3, 5, 8, 10}
FLAT_MINOR = {0, 2, 5, 7, 10}

# Perfiles de Krumhansl-Schmuckler
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def key_name(tonic: int, minor: bool) -> str:
    tonic %= 12
    flats = tonic in (FLAT_MINOR if minor else FLAT_MAJOR)
    name = (NOTES_FLAT if flats else NOTES_SHARP)[tonic]
    return name + ("m" if minor else "")


def detect_key(y: np.ndarray, sr: int):
    """Devuelve (tónica 0-11, es_menor, confianza)."""
    import librosa

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    profile = chroma.mean(axis=1)
    best = (0, False, -2.0)
    for tonic in range(12):
        for minor, ref in ((False, MAJOR_PROFILE), (True, MINOR_PROFILE)):
            r = np.corrcoef(profile, np.roll(ref, tonic))[0, 1]
            if r > best[2]:
                best = (tonic, minor, float(r))
    return best


def transpose_label(tonic: int, minor: bool, semitones: int) -> str:
    sign = f"+{semitones}" if semitones > 0 else str(semitones)
    return f"{key_name(tonic, minor)} → {key_name(tonic + semitones, minor)} ({sign} st)"


def pitch_shift(y: np.ndarray, sr: int, semitones: int) -> np.ndarray:
    """Transpone sin alterar el tempo. y puede ser (canales, muestras)."""
    if semitones == 0:
        return y
    import librosa

    if y.ndim == 1:
        return librosa.effects.pitch_shift(y, sr=sr, n_steps=semitones, res_type="soxr_hq")
    return np.stack([librosa.effects.pitch_shift(c, sr=sr, n_steps=semitones, res_type="soxr_hq") for c in y])
