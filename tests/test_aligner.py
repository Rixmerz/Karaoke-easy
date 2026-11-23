import numpy as np

from karaoke_easy.aligner import FRAME, ctc_align, romanize, trim_to_voice


def test_romanize_spanish():
    assert romanize("Mañana") == "manana"
    assert romanize("¿Verás?") == "veras"


def test_ctc_align_finds_token_positions():
    T, C = 50, 5
    em = np.full((T, C), -10.0)
    em[:, 0] = -0.1                      # blank por defecto
    for tok, frames in [(1, range(10, 13)), (2, range(30, 33)), (2, range(40, 42))]:
        for f in frames:
            em[f, :] = -10.0
            em[f, tok] = -0.1
    em[35:38, :] = -10.0; em[35:38, 0] = -0.1   # blank entre las dos '2' repetidas
    (first, last), score = ctc_align(em, [1, 2, 2])
    assert list(first) == [10, 30, 40] and list(last) == [12, 32, 41]
    assert score > -1


def test_trim_to_voice_cuts_long_tail():
    voiced = np.zeros(1000, bool)
    voiced[100:150] = True                # 2.0 s – 3.0 s con voz
    e = trim_to_voice(2.0, 15.0, voiced)
    assert abs(e - 3.0) < 1e-6
    assert trim_to_voice(10.0, 12.0, voiced) == 10.4    # sin voz: duración mínima
    assert FRAME == 0.02


def test_silence_bias_and_start_to_voice():
    import numpy as np
    from karaoke_easy import aligner as a
    v = np.zeros(300, bool); v[50:100] = True; v[200:250] = True
    em = np.log(np.full((300, 29), 1 / 29))
    b = a.silence_bias(em, v)
    assert b[150, 1] < em[150, 1] and b[150, 0] == em[150, 0] and b[60, 1] == em[60, 1]
    assert a.start_to_voice(0.9, 1.5, v) == 1.0



def test_ctc_long_line_no_overflow():
    import numpy as np
    from karaoke_easy import aligner as a
    toks = [(i % 27) + 1 for i in range(200)]  # >63 letras: antes desbordaba int8
    T = 600
    em = np.full((T, 29), -10.0)
    em[:, 0] = -0.1
    for i, k in enumerate(toks):
        em[i * 3 + 1, k] = -0.01
    res, score = a.ctc_align(em, toks)
    assert res is not None and res[0][0] <= res[0][-1]
