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
        b = KaraokeBuilder(Options(path, ".", semitones=-2, whisper_model="base", width=640, height=360),
                           log=lambda m: print(m, flush=True))
        b.run()
        return 0
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        log.flush()


if __name__ == "__main__":
    if os.environ.get("KARAOKE_SELFTEST"):
        import multiprocessing

        multiprocessing.freeze_support()
        sys.exit(selftest(os.environ["KARAOKE_SELFTEST"]))
    from karaoke_easy.app import main

    main()
