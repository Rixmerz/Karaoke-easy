"""Proceso completo: audio -> separación de voz -> letra con tiempos -> tono -> vídeo karaoke."""
import hashlib
import json
import os
import random
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import music, paths
from .subtitles import Word, build_ass

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
SR = 44100
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # oculta consola de ffmpeg en Windows


@dataclass
class Options:
    input_path: str
    output_dir: str
    semitones: int = 0
    whisper_model: str = "small"
    language: str | None = None  # None = autodetectar
    use_source_video: bool = True
    width: int = 1920
    height: int = 1080
    device: str = "auto"  # auto | cpu | cuda
    guide_track: bool = True
    make_video: bool = True  # crear el MP4 y el MP3 además del paquete del reproductor
    lyrics_text: str | None = None  # letra correcta (LRC o texto plano); None = solo Whisper
    auto_lyrics: bool = True
    artist_hint: str = ""  # artista/título para buscar la letra (p. ej. desde los datos del enlace)
    title_hint: str = ""  # buscar la letra en LRCLIB si no se entrega  # añade pista de audio alternativa con la voz


def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(args, cwd=None):
    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", *args]
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg falló:\n" + p.stderr[-2000:])


def _device(pref):
    if pref != "auto":
        return pref
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


class Cancelled(Exception):
    pass


class KaraokeBuilder:
    def __init__(self, opts: Options, log=print, progress=lambda p: None, cancel_event=None,
                 step=lambda key: None):
        self.cancel_event = cancel_event
        self.step = step  # pasos genéricos para la interfaz: prepare, separate, lyrics, sync, video, finish
        self.package = None
        from .downloader import download, is_url

        if is_url(opts.input_path):
            dl_dir = Path(opts.output_dir) / "descargas"
            path, artist, title = download(opts.input_path, dl_dir, want_video=opts.use_source_video,
                                           log=log, progress=progress)
            opts.input_path = str(path)
            opts.artist_hint = opts.artist_hint or artist
            opts.title_hint = opts.title_hint or title
        self.o = opts
        self.log = log
        self.progress = progress
        self.src = Path(opts.input_path).resolve()
        self.name = self.src.stem
        self.out = Path(opts.output_dir).resolve() / f"{self.name}_karaoke"
        self.work = self.out / "_trabajo"
        self.work.mkdir(parents=True, exist_ok=True)
        self.device = _device(opts.device)
        self.key = None
        self.rhythm = None
        self.aligned_lines = 0
        paths.setup_offline()

    # 1 ------------------------------------------------------------------
    def extract_audio(self) -> Path:
        self.log("Extrayendo audio…")
        wav = self.work / "original.wav"
        run_ffmpeg(["-i", str(self.src), "-vn", "-ac", "2", "-ar", str(SR), "-c:a", "pcm_s16le", str(wav)])
        return wav

    # 2 ------------------------------------------------------------------
    def separate(self, wav: Path):
        inst, voc = self.work / "instrumental.wav", self.work / "voz.wav"
        if inst.exists() and voc.exists():
            self.log("Separación ya existente, reutilizando.")
            return inst, voc
        self.log(f"Quitando la voz con Demucs (htdemucs, {self.device})… puede tardar varios minutos.")
        import soundfile as sf
        import torch
        from demucs.apply import apply_model
        from demucs.pretrained import get_model

        if (paths.DEMUCS_DIR / "htdemucs.yaml").exists():
            model = get_model("htdemucs", repo=paths.DEMUCS_DIR)  # archivo incluido, sin escribir nada
        else:
            model = get_model("htdemucs")
        model.to(self.device).eval()
        data, sr = sf.read(str(wav), dtype="float32", always_2d=True)
        mix = torch.from_numpy(data.T.copy())
        ref = mix.mean(0)
        mix = (mix - ref.mean()) / (ref.std() + 1e-8)
        with torch.no_grad():
            src = apply_model(model, mix[None].to(self.device), device=self.device,
                              split=True, overlap=0.25, progress=False)[0].cpu()
        src = src * (ref.std() + 1e-8) + ref.mean()
        vi = model.sources.index("vocals")
        vocals = src[vi]
        accomp = sum(src[i] for i in range(len(model.sources)) if i != vi)
        sf.write(str(voc), vocals.numpy().T, sr)
        sf.write(str(inst), accomp.numpy().T, sr)
        return inst, voc

    # 3 ------------------------------------------------------------------
    def transcribe(self, vocals: Path):
        manual = self.work / "letra_manual.json"
        if manual.exists():
            self.log("Usando letra_manual.json (tiempos editados a mano).")
            return [Word(**w) for w in json.loads(manual.read_text(encoding="utf-8"))]
        asr = self._whisper(vocals)
        lines = self.get_lyrics()
        if not lines:
            words = asr
        else:
            from .lyrics import align

            words = align(lines, asr)
            self.log(f"Letra alineada con el audio: {len(lines)} líneas, {len(words)} palabras.")
            self.step("sync")
            words = self.refine(words, vocals)
        (self.work / "letra.json").write_text(json.dumps([w.__dict__ for w in words], ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        return words

    def fit_rhythm(self, words, inst: Path, voc: Path):
        """Detecta pulso/compás y cuadra el inicio de las palabras con los ataques de la voz y el pulso."""
        try:
            import librosa
            from . import rhythm

            y, sr = librosa.load(str(inst), sr=22050, mono=True)
            self.rhythm = rhythm.analyze(y, sr)
            self.log(f"Tempo: {self.rhythm.tempo:.0f} BPM, {len(self.rhythm.downbeats)} compases.")
            v, _ = librosa.load(str(voc), sr=22050, mono=True)
            words, moved = rhythm.snap_words(words, rhythm.vocal_onsets(v, sr), rhythm.grid(self.rhythm.beats))
            self.log(f"Palabras cuadradas con el ritmo: {moved}/{len(words)} (ajustes de < 80 ms).")
            (self.work / "letra_final.json").write_text(
                json.dumps([w.__dict__ for w in words], ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            self.log(f"Análisis rítmico no disponible ({e}).")
        return words

    def refine(self, words, vocals: Path):
        """Afina cada palabra con alineación forzada (MMS_FA) dentro de la ventana de su verso."""
        try:
            from . import aligner
            from .lyrics import split_lines
            import librosa
        except Exception as e:
            self.log(f"Alineación forzada no disponible ({e}).")
            return words
        self.log("Afinando la sincronización palabra a palabra (alineación forzada)…")
        lines = split_lines(words)
        wins = []
        for i, ln in enumerate(lines):
            nxt = lines[i + 1][0].start if i + 1 < len(lines) else ln[-1].end + 3
            wins.append((ln[0].start - 1.5, max(ln[-1].end, nxt) + 1.0))
        audio, _ = librosa.load(str(vocals), sr=aligner.SR, mono=True)
        try:
            try:
                out = aligner.align_global(audio, lines, wins, device=self.device, log=self.log)
                if aligner.align_global.last_score > -1.5:
                    self.aligned_lines = len(lines)
                    return out
                self.log("Confianza baja en la alineación global; se alinea verso a verso.")
            except Exception as e:
                self.log(f"Alineación global no disponible ({e}); se alinea verso a verso.")
            out = aligner.align_lines(audio, lines, wins, device=self.device, log=self.log)
            self.aligned_lines = getattr(aligner.align_lines, "last_refined", 0)
            return out
        except Exception as e:
            self.log(f"Alineación forzada falló ({e}); se mantiene la sincronización aproximada.")
            return words

    def get_lyrics(self):
        from . import lyrics

        text = self.o.lyrics_text
        if not text and self.o.auto_lyrics:
            artist, title = lyrics.guess_artist_title(self.src.stem)
            if self.o.title_hint:
                artist, title = self.o.artist_hint or artist, self.o.title_hint
            try:
                import soundfile as sf

                dur = sf.info(str(self.work / "original.wav")).duration
                r = lyrics.search(artist, title, dur)
            except Exception as e:  # sin internet, etc.
                self.log(f"No se pudo buscar la letra en LRCLIB ({e}); se usa la transcripción de Whisper.")
                r = None
            if r:
                self.log(f"Letra encontrada en LRCLIB: {r.get('artistName')} - {r.get('trackName')}")
                text = r.get("syncedLyrics") or r.get("plainLyrics")
            else:
                self.log("Letra no encontrada en LRCLIB; se usa la transcripción de Whisper.")
        if text:
            (self.work / "letra_original.txt").write_text(text, encoding="utf-8")
        return lyrics.parse_lyrics(text) if text else None

    def _whisper(self, vocals: Path):
        cache = self.work / "whisper.json"
        if cache.exists():
            self.log("Transcripción de Whisper ya existente, reutilizando.")
            return [Word(**w) for w in json.loads(cache.read_text(encoding="utf-8"))]
        self.log(f"Transcribiendo la letra con Whisper ({self.o.whisper_model})…")
        from faster_whisper import WhisperModel

        ctype = "float16" if self.device == "cuda" else "int8"
        local = paths.whisper_dir(self.o.whisper_model)
        src = str(local) if (local / "model.bin").exists() else self.o.whisper_model
        model = WhisperModel(src, device=self.device, compute_type=ctype)
        import librosa

        audio, _ = librosa.load(str(vocals), sr=16000, mono=True)  # evita depender de PyAV
        segments, info = model.transcribe(audio, language=self.o.language, word_timestamps=True,
                                          vad_filter=True, beam_size=5,
                                          condition_on_previous_text=False)
        self.log(f"Idioma detectado: {info.language}")
        words = []
        for seg in segments:
            for w in seg.words or []:
                if w.word.strip():
                    words.append(Word(w.word.strip(), float(w.start), float(w.end)))
        cache.write_text(json.dumps([w.__dict__ for w in words], ensure_ascii=False, indent=1), encoding="utf-8")
        self.log(f"{len(words)} palabras detectadas.")
        return words

    # 4 ------------------------------------------------------------------
    def detect_key(self, inst: Path):
        import librosa

        y, sr = librosa.load(str(inst), sr=22050, mono=True, duration=240)
        tonic, minor, conf = music.detect_key(y, sr)
        self.key = (tonic, minor)
        self.log(f"Tonalidad detectada: {music.key_name(tonic, minor)} (confianza {conf:.2f})")
        return tonic, minor

    def transpose(self, inst: Path, label=True) -> Path:
        st = self.o.semitones
        if st == 0:
            return inst
        if label:
            self.log("Transponiendo: " + music.transpose_label(*self.key, st))
        import soundfile as sf

        y, sr = sf.read(str(inst), dtype="float32", always_2d=True)
        shifted = music.pitch_shift(y.T, sr, st).T
        peak = np.abs(shifted).max()
        if peak > 0.99:
            shifted *= 0.99 / peak
        out = self.work / f"{inst.stem}_{st:+d}.wav"
        sf.write(str(out), shifted, sr)
        return out

    # 5 ------------------------------------------------------------------
    def palette(self):
        seed = int(hashlib.md5(self.name.encode("utf-8")).hexdigest(), 16) % (2**32)
        rnd = random.Random(seed)
        hue = rnd.random()
        return rnd, hue

    def make_background(self) -> Path:
        """Fondo único generado a partir del nombre de la canción."""
        from PIL import Image, ImageDraw, ImageFilter
        import colorsys

        rnd, hue = self.palette()
        W, H = self.o.width, self.o.height

        def rgb(h, s, v):
            return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h % 1, s, v))

        c1, c2 = np.array(rgb(hue, 0.8, 0.35)), np.array(rgb(hue + 0.15 + rnd.random() * 0.3, 0.9, 0.12))
        yy, xx = np.mgrid[0:H, 0:W]
        ang = rnd.random() * np.pi
        t = (np.cos(ang) * xx / W + np.sin(ang) * yy / H)
        t = (t - t.min()) / (t.max() - t.min())
        img = (c1 * (1 - t[..., None]) + c2 * t[..., None]).astype(np.uint8)
        im = Image.fromarray(img, "RGB")
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for _ in range(rnd.randint(14, 26)):
            r = rnd.randint(H // 20, H // 4)
            x, y = rnd.randint(-r, W), rnd.randint(-r, H)
            col = rgb(hue + rnd.uniform(-0.2, 0.4), rnd.uniform(0.4, 0.9), rnd.uniform(0.5, 1.0))
            d.ellipse([x, y, x + r * 2, y + r * 2], fill=col + (rnd.randint(20, 60),))
        layer = layer.filter(ImageFilter.GaussianBlur(H // 60))
        im = Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")
        path = self.work / "fondo.png"
        im.save(path)
        return path

    def ass_palette(self):
        import colorsys

        _, hue = self.palette()
        r, g, b = (int(c * 255) for c in colorsys.hsv_to_rgb((hue + 0.5) % 1, 0.75, 1.0))
        return {"sung": f"&H00{b:02X}{g:02X}{r:02X}", "unsung": "&H00FFFFFF", "outline": "&H00101010"}, (r, g, b)

    def guide_mix(self, inst: Path, voc: Path) -> Path:
        """Pista 'con voz guía': instrumental + voz (ambas ya transpuestas)."""
        import soundfile as sf

        a, sr = sf.read(str(inst), dtype="float32", always_2d=True)
        v, _ = sf.read(str(voc), dtype="float32", always_2d=True)
        n = min(len(a), len(v))
        mix = a[:n] + v[:n]
        peak = np.abs(mix).max()
        if peak > 0.99:
            mix *= 0.99 / peak
        out = self.work / f"con_voz_{self.o.semitones:+d}.wav"
        sf.write(str(out), mix, sr)
        return out

    def render(self, words, audio: Path, suffix: str, guide: Path | None = None) -> Path:
        W, H = self.o.width, self.o.height
        pal, (r, g, b) = self.ass_palette()
        title = self.name
        if self.key:
            k = self.key
            title += f"\\NTono: {music.key_name(k[0] + self.o.semitones, k[1])}"
            if self.o.semitones:
                title += f" ({self.o.semitones:+d})"
        beats = self.rhythm.beats if self.rhythm is not None else None
        (self.work / "karaoke.ass").write_text(build_ass(words, title, pal, W, H, beats=beats), encoding="utf-8-sig")
        out = self.out / f"{self.name}_karaoke{suffix}.mp4"
        wave_col = f"0x{r:02X}{g:02X}{b:02X}"
        use_video = self.o.use_source_video and self.src.suffix.lower() in VIDEO_EXT
        if use_video:
            self.log("Renderizando vídeo sobre el vídeo original…")
            vin = ["-i", str(self.src)]
            base = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                    f"boxblur=6:1,eq=brightness=-0.25:saturation=0.8,fps=30[bg]")
        else:
            self.log("Renderizando vídeo con fondo generado…")
            bg = self.make_background()
            vin = ["-loop", "1", "-framerate", "30", "-i", str(bg)]
            base = "[0:v]format=yuv420p[bg]"
        fc = (f"{base};[1:a]showwaves=s={W}x{H // 6}:mode=cline:rate=30:colors={wave_col}@0.55,format=rgba[w];"
              f"[bg][w]overlay=0:H-h-{H // 30}:shortest=1,ass=karaoke.ass,format=yuv420p[v]")
        gin, gmap = [], []
        if guide is not None:
            gin = ["-i", str(guide.resolve())]
            gmap = ["-map", "2:a", "-metadata:s:a:1", "title=Con voz guía", "-metadata:s:a:1", "language=spa",
                    "-disposition:a:1", "0"]
        run_ffmpeg([*vin, "-i", str(audio.resolve()), *gin, "-filter_complex", fc, "-map", "[v]", "-map", "1:a",
                    *gmap, "-metadata:s:a:0", "title=Karaoke (sin voz)", "-disposition:a:0", "default",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart", str(out.resolve())], cwd=str(self.work))
        return out

    def export_audio(self, audio: Path, suffix: str, kind="pista") -> Path:
        out = self.out / f"{self.name}_{kind}{suffix}.mp3"
        run_ffmpeg(["-i", str(audio), "-c:a", "libmp3lame", "-b:a", "320k", str(out)])
        return out

    # -------------------------------------------------------------------
    def check_cancel(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise Cancelled("Proceso cancelado por el usuario.")

    def run(self):
        steps = 6
        self.progress(0)
        self.step("prepare")
        wav = self.extract_audio(); self.progress(1 / steps)
        self.check_cancel()
        self.step("separate")
        inst, voc = self.separate(wav); self.progress(2 / steps)
        self.check_cancel()
        self.step("lyrics")
        words = self.transcribe(voc)
        self.step("sync")
        words = self.fit_rhythm(words, inst, voc); self.progress(3 / steps)
        self.check_cancel()
        self.step("video")
        self.detect_key(inst)
        if not self.o.make_video:
            # Solo el reproductor de la app: sin vídeo ni MP3 (es lo más lento de todo el proceso)
            self.step("finish")
            self.log("Preparando la canción para el reproductor…")
            from .library import write_package
            self.package = write_package(self, words, inst, voc, run_ffmpeg)
            self.progress(1)
            self.words = words
            self.log("Listo. (El video MP4 está desactivado en Ajustes.)")
            return None, None
        track = self.transpose(inst); self.progress(4 / steps)
        self.check_cancel()
        suffix = "" if self.o.semitones == 0 else f"_{music.key_name(self.key[0] + self.o.semitones, self.key[1])}"
        suffix = suffix.replace("#", "s")
        guide = None
        if self.o.guide_track:
            self.log("Creando pista con voz guía…")
            guide = self.guide_mix(track, self.transpose(voc, label=False))
            self.export_audio(guide, suffix, "con_voz")
        mp3 = self.export_audio(track, suffix); self.progress(5 / steps)
        self.check_cancel()
        video = self.render(words, track, suffix, guide)
        self.check_cancel()
        self.step("finish")
        self.log("Preparando la canción para el reproductor…")
        from .library import write_package
        self.package = write_package(self, words, inst, voc, run_ffmpeg)
        self.progress(1)
        self.words = words
        self.log(f"Listo:\n  Vídeo: {video}\n  Pista: {mp3}")
        if guide is not None:
            self.log("El vídeo tiene 2 pistas de audio: 'Karaoke (sin voz)' y 'Con voz guía'. "
                     "Cámbielas en cualquier momento desde el reproductor (VLC: tecla B; "
                     "Reproductor multimedia de Windows: menú ⋯ › Idioma de audio).")
        return video, mp3


def analyze_key(path: str):
    """Análisis rápido de tono sobre el archivo original (para la interfaz)."""
    import soundfile as sf
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        run_ffmpeg(["-i", path, "-vn", "-ac", "1", "-ar", "22050", "-t", "240", wav])
        y, sr = sf.read(wav, dtype="float32")
        return music.detect_key(y, sr)
