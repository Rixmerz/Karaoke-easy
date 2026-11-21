"""Uso sin interfaz: python cli.py cancion.mp3 --semitonos -2"""
import argparse

from karaoke_easy.pipeline import KaraokeBuilder, Options

ap = argparse.ArgumentParser(description="Karaoke Easy (línea de comandos)")
ap.add_argument("entrada")
ap.add_argument("-o", "--salida", default=".")
ap.add_argument("-s", "--semitonos", type=int, default=0)
ap.add_argument("-m", "--modelo", default="small")
ap.add_argument("-l", "--idioma", default=None)
ap.add_argument("--sin-video-original", action="store_true")
a = ap.parse_args()
KaraokeBuilder(Options(a.entrada, a.salida, a.semitonos, a.modelo, a.idioma, not a.sin_video_original)).run()
