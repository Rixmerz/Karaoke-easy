import re

import numpy as np
import pytest

from karaoke_easy import music
from karaoke_easy.subtitles import Word, build_ass, countdowns, group_lines

PAL = {"sung": "&H0000FFFF", "unsung": "&H00FFFFFF", "outline": "&H00000000"}


@pytest.mark.parametrize("tonic,minor,name", [(0, False, "C"), (1, False, "Db"), (6, False, "F#"),
                                              (9, True, "Am"), (1, True, "C#m"), (10, False, "Bb"),
                                              (3, True, "Ebm"), (8, True, "G#m")])
def test_key_names_american(tonic, minor, name):
    assert music.key_name(tonic, minor) == name


def test_transpose_label_wraps():
    assert music.transpose_label(11, False, 2) == "B → Db (+2 st)"
    assert music.transpose_label(9, True, -2) == "Am → Gm (-2 st)"


def _chord(freqs, sr=22050, sec=6):
    t = np.arange(sr * sec) / sr
    return (sum(np.sin(2 * np.pi * f * t) for f in freqs) * 0.2).astype("float32"), sr


@pytest.mark.parametrize("freqs,expected", [([261.63, 329.63, 392.0, 130.81], "C"),
                                            ([220.0, 261.63, 329.63, 110.0], "Am"),
                                            ([392.0, 493.88, 587.33, 196.0], "G")])
def test_detect_key(freqs, expected):
    y, sr = _chord(freqs)
    t, m, _ = music.detect_key(y, sr)
    assert music.key_name(t, m) == expected


def test_pitch_shift_changes_frequency_keeps_length():
    sr = 22050
    t = np.arange(sr * 2) / sr
    y = np.sin(2 * np.pi * 440 * t).astype("float32")
    out = music.pitch_shift(np.stack([y, y]), sr, 2)
    assert out.shape == (2, len(y))
    spec = np.abs(np.fft.rfft(out[0]))
    f = np.argmax(spec) * sr / len(y)
    assert abs(f - 440 * 2 ** (2 / 12)) < 5  # ≈ 493.9 Hz (B)


def words_at(starts):
    return [Word(f"w{i}", s, s + 0.4) for i, s in enumerate(starts)]


def test_countdown_on_intro_and_long_gap_only():
    w = words_at([8.0, 8.5, 9.0, 9.5, 20.0, 20.5])  # intro 8 s, hueco ~10 s
    lines = group_lines(w)
    assert len(lines) == 2
    cds = countdowns(lines)
    assert len(cds) == 2
    assert "0:00:04.00,0:00:08.00" in cds[0]          # 4 s antes de la voz
    assert cds[0].count("●") == 4 and "\\kf100" in cds[0]


def test_no_countdown_when_singing_continuous():
    w = words_at([0.5 + i * 0.5 for i in range(30)])
    assert countdowns(group_lines(w)) == []


def test_ass_karaoke_timing():
    w = [Word("Hola", 5.0, 5.5), Word("mundo", 5.5, 6.2)]
    ass = build_ass(w, "Mi canción", PAL)
    assert "{\\kf50}Hola {\\kf70}mundo" in ass
    assert re.search(r"Dialogue: 0,0:00:00.00,.*,Title,", ass)
    assert "Dots" in ass


def test_ass_escapes_braces():
    ass = build_ass([Word("{x}", 1, 2)], "t", PAL)
    assert "(x)" in ass
