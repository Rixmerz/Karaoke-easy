import os
import sys


def selftest(path):
    """Procesa un archivo sin interfaz (usado por la integración continua)."""
    import traceback

    log = open("selftest.log", "w", encoding="utf-8")
    sys.stdout = sys.stderr = log
    try:
        from karaoke_easy import paths
        from karaoke_easy.pipeline import KaraokeBuilder, Options

        print("Modelos incluidos:", paths.bundled_whisper_models(), "en", paths.MODELS_DIR)
        from karaoke_easy.downloader import deno_path
        print("Deno (para YouTube):", deno_path())
        assert deno_path(), "falta Deno en el paquete"
        b = KaraokeBuilder(Options(path, os.environ.get("KARAOKE_OUT", "."), semitones=-2, whisper_model="small", width=640, height=360,
                                   lyrics_text=os.environ.get("KARAOKE_LYRICS") or None),
                           log=lambda m: print(m, flush=True))
        video, mp3 = b.run()
        words = " ".join(w.text for w in b.words).lower()
        print("PALABRAS:", words)
        expect = os.environ.get("KARAOKE_EXPECT", "").lower().split()
        found = [w for w in expect if w in words]
        print(f"Esperadas encontradas: {len(found)}/{len(expect)} {found}")
        assert video.stat().st_size > 50_000, "vídeo vacío"
        assert mp3.exists() and (video.parent / mp3.name.replace("_pista", "_con_voz")).exists(), "faltan MP3"
        assert not expect or len(found) >= len(expect) // 2, "la transcripción no reconoce la letra"
        if os.environ.get("KARAOKE_LYRICS"):
            assert b.aligned_lines > 0, "la alineación forzada (MMS_FA) no refinó ningún verso"
            print(f"MMS_FA refinó {b.aligned_lines} versos")
        assert b.package is not None and (b.package / "cancion.json").exists(), "falta el paquete del reproductor"
        print("Paquete del reproductor:", b.package)
        print("SELFTEST OK")
        return 0
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        log.flush()


if __name__ == "__main__":
    import multiprocessing as _mp

    _mp.freeze_support()  # necesario para los procesos de trabajo en el .exe
    if "--worker" in sys.argv:
        from karaoke_easy.jobs import worker_main

        worker_main(sys.argv[sys.argv.index("--worker") + 1])
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)  # salir aunque alguna librería deje hilos abiertos
    if "--serve" in sys.argv:
        from karaoke_easy.engine import main as engine_main

        engine_main(sys.argv[1:])
        sys.exit(0)
    if "--player" in sys.argv:
        import multiprocessing

        multiprocessing.freeze_support()
        from karaoke_easy.player_main import main as player_main

        player_main(sys.argv[1:])
        sys.exit(0)
    if os.environ.get("KARAOKE_SELFTEST"):
        import multiprocessing

        multiprocessing.freeze_support()
        sys.exit(selftest(os.environ["KARAOKE_SELFTEST"]))
    from karaoke_easy.app import main

    main()
