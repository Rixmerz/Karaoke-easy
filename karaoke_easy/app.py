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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Karaoke Easy")
        self.geometry("760x620")
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

        ttk.Label(f, text="Archivo (MP4 / MP3 / WAV):").grid(row=0, column=0, sticky="w", **pad)
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

        self.btn = ttk.Button(f, text="▶  Crear karaoke", command=self.start)
        self.btn.grid(row=4, column=0, columnspan=3, sticky="ew", **pad)
        self.bar = ttk.Progressbar(f, maximum=1.0)
        self.bar.grid(row=5, column=0, columnspan=3, sticky="ew", **pad)

        self.logbox = tk.Text(f, height=12, state="disabled", wrap="word")
        self.logbox.grid(row=6, column=0, columnspan=3, sticky="nsew", **pad)
        f.rowconfigure(6, weight=1)
        self.update_target()
        self.after(100, self.poll)

    # ---------------------------------------------------------------
    def pick_in(self):
        p = filedialog.askopenfilename(filetypes=FILETYPES)
        if p:
            self.in_var.set(p)
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
                elif kind == "done":
                    self.busy = False
                    self.btn.configure(state="normal")
                    if val:
                        messagebox.showinfo("Karaoke Easy", "¡Karaoke creado!\n\n" + val)
                elif kind == "error":
                    self.busy = False
                    self.btn.configure(state="normal")
                    messagebox.showerror("Error", val)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def _thread(self, fn):
        def wrap():
            try:
                fn()
            except Exception as e:
                self.log(traceback.format_exc())
                self.q.put(("error", str(e)))
        threading.Thread(target=wrap, daemon=True).start()

    def analyze(self):
        path = self.in_var.get()
        if not Path(path).is_file():
            return messagebox.showwarning("Karaoke Easy", "Seleccione un archivo primero.")
        self.log("Analizando tonalidad…")

        def job():
            from .pipeline import analyze_key
            k = analyze_key(path)
            self.q.put(("key", k))
            self.log(f"Tono detectado: {music.key_name(k[0], k[1])}")
        self._thread(job)

    def start(self):
        if self.busy:
            return
        path = self.in_var.get()
        if not Path(path).is_file():
            return messagebox.showwarning("Karaoke Easy", "Seleccione un archivo MP4, MP3 o WAV.")
        from .pipeline import KaraokeBuilder, Options

        opts = Options(input_path=path, output_dir=self.out_var.get(), semitones=int(self.st_var.get()),
                       whisper_model=self.model_var.get(), language=LANGS[self.lang_var.get()],
                       use_source_video=self.video_var.get(), guide_track=self.guide_var.get())
        self.busy = True
        self.btn.configure(state="disabled")

        def job():
            b = KaraokeBuilder(opts, log=self.log, progress=lambda p: self.q.put(("prog", p)))
            video, mp3 = b.run()
            self.q.put(("key", (*b.key, 1.0)))
            self.q.put(("done", f"Vídeo: {video}\nPista: {mp3}"))
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
