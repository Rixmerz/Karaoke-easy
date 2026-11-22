"""Interfaz gráfica (Tkinter) de Karaoke Easy."""
import queue
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import music, paths

LANGS = {"Autodetectar": None, "Español": "es", "Inglés": "en", "Portugués": "pt",
         "Italiano": "it", "Francés": "fr", "Alemán": "de"}
MODELS = paths.bundled_whisper_models() or ["tiny", "base", "small", "medium", "large-v3"]
FILETYPES = [("Audio/Vídeo", "*.mp4 *.mp3 *.wav *.m4a *.flac *.mkv *.mov"), ("Todos", "*.*")]


def _ver(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Karaoke Easy")
        self.geometry("820x860")
        self.minsize(640, 520)
        self.q = queue.Queue()
        self.key = None
        self.busy = False

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar(value=str(Path.home() / "Videos"))
        self.st_var = tk.IntVar(value=0)
        self.model_var = tk.StringVar(value="small" if "small" in MODELS else MODELS[-1])
        self.lang_var = tk.StringVar(value="Autodetectar")
        self.video_var = tk.BooleanVar(value=True)
        self.guide_var = tk.BooleanVar(value=True)
        self.key_var = tk.StringVar(value="Tono original: (sin analizar)")
        self.target_var = tk.StringVar(value="")

        pad = dict(padx=8, pady=4)
        f = ttk.Frame(self, padding=10)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text="Archivo(s) o enlace(s):").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(f, textvariable=self.in_var).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(f, text="Buscar…", command=self.pick_in).grid(row=0, column=2, **pad)

        ttk.Label(f, text="Carpeta de salida:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(f, textvariable=self.out_var).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(f, text="Buscar…", command=self.pick_out).grid(row=1, column=2, **pad)

        tone = ttk.LabelFrame(f, text="Tonalidad (clave americana)", padding=8)
        tone.grid(row=2, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(tone, textvariable=self.key_var, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(tone, text="Analizar tono", command=self.analyze).grid(row=0, column=1, padx=10)
        ttk.Label(tone, text="Transponer (semitonos):").grid(row=1, column=0, sticky="w", pady=6)
        sb = ttk.Spinbox(tone, from_=-12, to=12, textvariable=self.st_var, width=5, command=self.update_target)
        sb.grid(row=1, column=1, sticky="w", padx=10)
        sb.bind("<KeyRelease>", lambda e: self.update_target())
        ttk.Label(tone, textvariable=self.target_var, foreground="#0a6").grid(row=1, column=2, sticky="w")

        opt = ttk.LabelFrame(f, text="Opciones", padding=8)
        opt.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(opt, text="Modelo de letra (Whisper):").grid(row=0, column=0, sticky="w")
        ttk.Combobox(opt, textvariable=self.model_var, values=MODELS, state="readonly", width=10).grid(row=0, column=1, padx=6)
        ttk.Label(opt, text="Idioma:").grid(row=0, column=2, sticky="w", padx=(16, 0))
        ttk.Combobox(opt, textvariable=self.lang_var, values=list(LANGS), state="readonly", width=13).grid(row=0, column=3, padx=6)
        ttk.Checkbutton(opt, text="Usar el vídeo original de fondo (si es MP4)", variable=self.video_var).grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opt, text="Incluir pista con voz guía (activable en cualquier momento desde el reproductor)",
                        variable=self.guide_var).grid(row=2, column=0, columnspan=4, sticky="w", pady=(4, 0))

        ly = ttk.LabelFrame(f, text="Letra (se alinea sola con la voz)", padding=8)
        ly.grid(row=4, column=0, columnspan=3, sticky="nsew", **pad)
        ly.columnconfigure(1, weight=1)
        ly.columnconfigure(3, weight=1)
        self.artist_var, self.title_var = tk.StringVar(), tk.StringVar()
        ttk.Label(ly, text="Artista:").grid(row=0, column=0, sticky="w")
        ttk.Entry(ly, textvariable=self.artist_var).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(ly, text="Canción:").grid(row=0, column=2, sticky="w")
        ttk.Entry(ly, textvariable=self.title_var).grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Button(ly, text="Buscar letra", command=self.find_lyrics).grid(row=0, column=4, padx=4)
        self.lyrics_box = tk.Text(ly, height=8, wrap="word", undo=True)
        self.lyrics_box.grid(row=1, column=0, columnspan=5, sticky="nsew", pady=(6, 0))
        ttk.Label(ly, foreground="#666", text="Vacío = se busca automáticamente en LRCLIB y, si no está, se usa la "
                  "transcripción de la IA. Puede pegar o corregir la letra aquí.").grid(row=2, column=0, columnspan=5, sticky="w")

        bf = ttk.Frame(f)
        bf.grid(row=7, column=0, columnspan=3, sticky="ew", **pad)
        bf.columnconfigure(0, weight=1)
        self.btn = ttk.Button(bf, text="▶  Crear karaoke", command=self.start)
        self.btn.grid(row=0, column=0, sticky="ew")
        self.cancel_btn = ttk.Button(bf, text="■ Cancelar", command=self.cancel, state="disabled")
        self.cancel_btn.grid(row=0, column=1, padx=(6, 0))
        ttk.Button(bf, text="🎤 Reproductor / Biblioteca", command=self.open_player).grid(row=0, column=2, padx=(6, 0))
        self.update_lbl = ttk.Label(f, foreground="#06c", cursor="hand2")
        self.update_lbl.grid(row=10, column=0, columnspan=3, sticky="w", padx=8)
        self.cancel_event = threading.Event()
        self.last_song = None
        threading.Thread(target=self.check_update, daemon=True).start()
        self.bar = ttk.Progressbar(f, maximum=1.0)
        self.bar.grid(row=8, column=0, columnspan=3, sticky="ew", **pad)

        self.logbox = tk.Text(f, height=7, state="disabled", wrap="word")
        self.logbox.grid(row=9, column=0, columnspan=3, sticky="nsew", **pad)
        f.rowconfigure(4, weight=2)
        f.rowconfigure(9, weight=1)
        self.update_target()
        self.after(100, self.poll)

    # ---------------------------------------------------------------
    def pick_in(self):
        ps = filedialog.askopenfilenames(filetypes=FILETYPES)
        if len(ps) > 1:
            self.in_var.set(" ; ".join(ps))
            self.artist_var.set("")
            self.title_var.set("")
            self.lyrics_box.delete("1.0", "end")
            self.log(f"{len(ps)} canciones en la cola: se procesarán una tras otra.")
            return
        p = ps[0] if ps else ""
        if p:
            self.in_var.set(p)
            from .lyrics import guess_artist_title
            a, t = guess_artist_title(Path(p).stem)
            self.artist_var.set(a)
            self.title_var.set(t)
            self.lyrics_box.delete("1.0", "end")
            self.key = None
            self.key_var.set("Tono original: (sin analizar)")
            self.update_target()

    def pick_out(self):
        p = filedialog.askdirectory()
        if p:
            self.out_var.set(p)

    def update_target(self):
        try:
            st = int(self.st_var.get())
        except (tk.TclError, ValueError):
            return
        if self.key:
            self.target_var.set("Nuevo tono: " + music.transpose_label(self.key[0], self.key[1], st))
        else:
            self.target_var.set(f"{st:+d} semitonos")

    def log(self, msg):
        self.q.put(("log", msg))

    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.logbox.configure(state="normal")
                    self.logbox.insert("end", val + "\n")
                    self.logbox.see("end")
                    self.logbox.configure(state="disabled")
                elif kind == "prog":
                    self.bar["value"] = val
                elif kind == "key":
                    self.key = val[:2]
                    self.key_var.set(f"Tono original: {music.key_name(*self.key)}  (confianza {val[2]:.2f})")
                    self.update_target()
                elif kind == "downloaded":
                    p, a, t = val
                    self.in_var.set(p)
                    if not self.title_var.get().strip():
                        self.artist_var.set(a)
                        self.title_var.set(t)
                elif kind == "lyrics":
                    self.lyrics_box.delete("1.0", "end")
                    self.lyrics_box.insert("1.0", val)
                elif kind == "done":
                    self.busy = False
                    self.btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
                    if val and messagebox.askyesno("Karaoke Easy", val + "\n\n¿Abrir ahora en el reproductor?"):
                        self.open_player(self.last_song)
                elif kind == "error":
                    self.busy = False
                    self.btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
                    if val:
                        messagebox.showerror("Error", val)
                elif kind == "update":
                    tag, url = val
                    self.update_lbl.configure(text=f"⬆ Hay una versión nueva ({tag}). Clic aquí para descargarla.")
                    self.update_lbl.bind("<Button-1>", lambda e, u=url: __import__("webbrowser").open(u))
                elif kind == "choose_lyrics":
                    self.choose_lyrics(val)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def _thread(self, fn):
        def wrap():
            try:
                fn()
            except Exception as e:
                from .pipeline import Cancelled
                if isinstance(e, Cancelled):
                    self.log("⏹ " + str(e))
                    self.q.put(("error", ""))
                    return
                self.log(traceback.format_exc())
                self.q.put(("error", str(e)))
        threading.Thread(target=wrap, daemon=True).start()

    def resolve_input(self, src=None):
        """Si la entrada es un enlace, lo descarga (en el hilo de trabajo) y devuelve la ruta local."""
        from .downloader import download, is_url

        src = (src if src is not None else self.in_var.get()).strip()
        if not is_url(src):
            return src, "", ""
        out = Path(self.out_var.get()) / "descargas"
        path, artist, title = download(src, out, want_video=self.video_var.get(), log=self.log,
                                       progress=lambda p: self.q.put(("prog", p)))
        if len(self.items()) == 1:
            self.q.put(("downloaded", (str(path), artist, title)))
        return str(path), artist, title

    def analyze(self):
        from .downloader import is_url
        path = self.in_var.get()
        if is_url(path):
            self.log("Descargando para analizar el tono…")

            def job_url():
                from .pipeline import analyze_key
                k = analyze_key(self.resolve_input()[0])
                self.q.put(("key", k))
                self.log(f"Tono detectado: {music.key_name(k[0], k[1])}")
            return self._thread(job_url)
        if not Path(path).is_file():
            return messagebox.showwarning("Karaoke Easy", "Seleccione un archivo primero.")
        self.log("Analizando tonalidad…")

        def job():
            from .pipeline import analyze_key
            k = analyze_key(path)
            self.q.put(("key", k))
            self.log(f"Tono detectado: {music.key_name(k[0], k[1])}")
        self._thread(job)

    def find_lyrics(self):
        if not self.title_var.get().strip():
            return messagebox.showwarning("Karaoke Easy", "Escriba el nombre de la canción.")
        self.log("Buscando letra en LRCLIB…")

        def job():
            from . import lyrics
            res = lyrics.search_all(self.artist_var.get().strip(), self.title_var.get().strip())
            if not res:
                self.log("No se encontró la letra. Puede pegarla en el cuadro.")
                return
            if len(res) == 1:
                r = res[0]
                self.log(f"Letra encontrada: {r.get('artistName')} - {r.get('trackName')} ({r.get('albumName')})")
                self.q.put(("lyrics", r.get("syncedLyrics") or r.get("plainLyrics")))
            else:
                self.log(f"{len(res)} versiones de la letra encontradas: elija una.")
                self.q.put(("choose_lyrics", res[:15]))
        self._thread(job)

    def items(self):
        import re
        return [p.strip() for p in re.split(r"\s*;\s*|\n", self.in_var.get()) if p.strip()]

    def cancel(self):
        self.cancel_event.set()
        self.log("Cancelando… (se detiene al terminar el paso actual)")

    def open_player(self, song_id=None):
        from .player_main import launch
        launch(song_id, extra_dirs=[self.out_var.get()])

    def check_update(self):
        try:
            import json
            import urllib.request
            req = urllib.request.Request("https://api.github.com/repos/Rixmerz/Karaoke-easy/releases/latest",
                                         headers={"User-Agent": "KaraokeEasy"})
            with urllib.request.urlopen(req, timeout=8) as r:
                rel = json.load(r)
            latest = rel.get("tag_name", "").lstrip("v")
            if latest and _ver(latest) > _ver(paths.app_version()):
                self.q.put(("update", (rel["tag_name"], rel.get("html_url"))))
        except Exception:
            pass

    def choose_lyrics(self, results):
        win = tk.Toplevel(self)
        win.title("Elija la versión de la letra")
        win.geometry("640x380")
        lb = tk.Listbox(win, activestyle="dotbox")
        lb.pack(fill="both", expand=True, padx=8, pady=8)
        for r in results:
            d = r.get("duration") or 0
            sync = "🕒 sincronizada" if r.get("syncedLyrics") else "texto"
            lb.insert("end", f"{r.get('artistName')} — {r.get('trackName')}  ·  {r.get('albumName') or ''}  ·  "
                             f"{int(d) // 60}:{int(d) % 60:02d}  ·  {sync}")
        lb.selection_set(0)

        def ok(_=None):
            sel = lb.curselection()
            if sel:
                r = results[sel[0]]
                self.lyrics_box.delete("1.0", "end")
                self.lyrics_box.insert("1.0", r.get("syncedLyrics") or r.get("plainLyrics"))
                self.log(f"Letra elegida: {r.get('artistName')} - {r.get('trackName')} ({r.get('albumName')})")
            win.destroy()
        lb.bind("<Double-1>", ok)
        ttk.Button(win, text="Usar esta letra", command=ok).pack(pady=(0, 8))

    def start(self):
        if self.busy:
            return
        from .downloader import is_url
        items = self.items()
        bad = [p for p in items if not is_url(p) and not Path(p).is_file()]
        if not items or bad:
            return messagebox.showwarning("Karaoke Easy", "Seleccione archivos MP4/MP3/WAV o pegue enlaces"
                                          + (f"\n\nNo encontrado: {bad[0]}" if bad else ""))
        from .pipeline import KaraokeBuilder, Options

        single = len(items) == 1
        base = dict(output_dir=self.out_var.get(), semitones=int(self.st_var.get()),
                    whisper_model=self.model_var.get(), language=LANGS[self.lang_var.get()],
                    use_source_video=self.video_var.get(), guide_track=self.guide_var.get())
        lyrics_text = self.lyrics_box.get("1.0", "end").strip() or None if single else None
        artist, title = self.artist_var.get().strip(), self.title_var.get().strip()
        self.busy = True
        self.cancel_event.clear()
        self.btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")

        def job():
            import time
            done, failed = [], []
            for i, src in enumerate(items, 1):
                if self.cancel_event.is_set():
                    break
                if not single:
                    self.log(f"\n===== Canción {i} de {len(items)}: {src} =====")
                t0 = time.time()
                try:
                    opts = Options(input_path=src, lyrics_text=lyrics_text, **base)
                    opts.input_path, opts.artist_hint, opts.title_hint = self.resolve_input(src)
                    if single and title and not opts.title_hint:
                        opts.artist_hint, opts.title_hint = artist, title

                    def prog(p, i=i):
                        self.q.put(("prog", ((i - 1) + p) / len(items)))
                    b = KaraokeBuilder(opts, log=self.log, progress=prog, cancel_event=self.cancel_event)
                    video, mp3 = b.run()
                    self.q.put(("key", (*b.key, 1.0)))
                    if b.package is not None:
                        from .library import song_id
                        self.last_song = song_id(b.package)
                    done.append(video)
                    self.log(f"Tiempo: {int(time.time() - t0) // 60} min {int(time.time() - t0) % 60} s")
                except Exception as e:
                    from .pipeline import Cancelled
                    if isinstance(e, Cancelled) or single:
                        raise
                    failed.append(src)
                    self.log(f"✖ Error con {src}: {e}")
            if not done:
                self.q.put(("error", "" if self.cancel_event.is_set() else "No se pudo procesar ninguna canción."))
                return
            msg = f"¡Listo! {len(done)} karaoke(s) creado(s)." + (f"\nCon errores: {len(failed)}" if failed else "")
            if single:
                msg = f"¡Karaoke creado!\n\nVídeo: {done[0]}"
            self.q.put(("done", msg))
        self._thread(job)

def main():
    import multiprocessing
    import os
    import sys

    multiprocessing.freeze_support()
    # En el .exe sin consola stdout/stderr son None y algunas librerías fallan al escribir
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    App().mainloop()


if __name__ == "__main__":
    main()
