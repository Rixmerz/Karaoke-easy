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
        print("SELFTEST OK")
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
