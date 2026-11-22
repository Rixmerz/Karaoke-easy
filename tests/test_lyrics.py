from karaoke_easy.lyrics import align, guess_artist_title, parse_lyrics
from karaoke_easy.subtitles import Word, group_lines


def test_guess_artist_title():
    assert guess_artist_title("3822164a-Soda_Stereo_-_En_la_Ciudad_de_la_Furia_Official_Video_-_SodaStereoVEVO") == \
        ("Soda Stereo", "En la Ciudad de la Furia")
    assert guess_artist_title("Artista - Tema (Lyrics)") == ("Artista", "Tema")


def test_parse_lrc_and_plain():
    assert parse_lyrics("[00:41.12] Hola mundo\n[01:02.00]\n[00:10.00] Antes") == [(10.0, "Antes"), (41.12, "Hola mundo")]
    assert parse_lyrics("uno dos\n\ntres") == [(None, "uno dos"), (None, "tres")]


def test_align_fixes_wrong_words_keeps_timing_and_lines():
    lines = parse_lyrics("[00:10.00] Me verás volar\n[00:14.00] por la ciudad de la furia")
    asr = [Word(t, 46 + i * 0.5, 46.4 + i * 0.5) for i, t in
           enumerate("verás velar por la ciudad de la furia".split())]  # 'Me' perdido, 'velar' mal
    out = align(lines, asr)
    assert [w.text.strip() for w in out] == "Me verás volar por la ciudad de la furia".split()
    assert out[1].start == 46.0                      # 'verás' toma el tiempo real
    assert out[2].start == 46.5                      # 'volar' ~ 'velar' (difuso)
    assert out[0].start < out[1].start               # 'Me' interpolado antes
    assert out[3].text.startswith("\n")              # salto de línea original
    assert [len(l) for l in group_lines(out)] == [3, 6]


def test_align_offset_for_unrecognized_line():
    lines = parse_lyrics("[00:10.00] uno dos tres\n[00:20.00] palabras jamas oidas\n[00:30.00] cuatro cinco seis")
    asr = [Word(t, s, s + 0.3) for t, s in [("uno", 45), ("dos", 45.5), ("tres", 46), ("cuatro", 65), ("cinco", 65.5), ("seis", 66)]]
    out = align(lines, asr)
    assert abs(out[3].start - 55.0) < 0.01           # 20 s + desfase de 35 s
    assert all(x.start <= y.start for x, y in zip(out, out[1:]))


def test_accents_recovered_from_whisper():
    from karaoke_easy.lyrics import with_accents
    assert with_accents("veras", "verás") == "verás"
    assert with_accents("Mi,", "mí") == "Mí,"
    assert with_accents("Cancion", "canción") == "Canción"
    assert with_accents("hola", "ola") == "hola"          # palabra distinta: no tocar
    lines = parse_lyrics("Me veras volar")
    out = align(lines, [Word("me", 1, 1.2), Word("verás", 1.3, 1.6), Word("volar", 1.7, 2)])
    assert [w.text for w in out] == ["Me", "verás", "volar"]
