"""Prueba de extremo a extremo con la separación y la transcripción simuladas."""
import re
import subprocess

import numpy as np
import soundfile as sf

from karaoke_easy.pipeline import KaraokeBuilder, Options, ffmpeg_exe
from karaoke_easy.subtitles import Word


def test_full_render(tmp_path):
    sr = 44100
    t = np.arange(sr * 10) / sr
    music_ = sum(np.sin(2 * np.pi * f * t) for f in [220, 261.63, 329.63]) * 0.15
    voice = np.sin(2 * np.pi * 880 * t) * 0.1 * (t > 5)
    src = tmp_path / "mi canción.wav"
    sf.write(src, np.stack([music_ + voice] * 2, 1), sr)
    inst, voc = tmp_path / "i.wav", tmp_path / "v.wav"
    sf.write(inst, np.stack([music_] * 2, 1), sr)
    sf.write(voc, np.stack([voice] * 2, 1), sr)

    b = KaraokeBuilder(Options(str(src), str(tmp_path), semitones=-2, width=640, height=360))
    b.separate = lambda w: (inst, voc)
    b.transcribe = lambda v: [Word(x, 5 + i * 0.6, 5.5 + i * 0.6) for i, x in enumerate("uno dos tres".split())]
    video, mp3 = b.run()

    assert video.name == "mi canción_karaoke_Gm.mp4" and video.stat().st_size > 10_000
    assert mp3.exists()
    assert (video.parent / "mi canción_con_voz_Gm.mp3").exists()
    info = subprocess.run([ffmpeg_exe(), "-i", str(video)], capture_output=True, text=True).stderr
    assert len(re.findall(r"Stream #0:\d+.*Audio", info)) == 2
    assert "Con voz guía" in info and "Karaoke (sin voz)" in info
    ass = (b.work / "karaoke.ass").read_text(encoding="utf-8-sig")
    assert "Dots" in ass and "●" in ass
