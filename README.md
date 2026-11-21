# Karaoke Easy 🎤

Programa para Windows que convierte una canción (**MP4, MP3, WAV**, también M4A/FLAC/MKV/MOV) en:

1. **Vídeo karaoke único** (MP4 1080p): letra sincronizada palabra por palabra con relleno de color, fondo generado a partir del nombre de la canción (colores/formas distintas para cada tema) o el vídeo original difuminado, y ondas de audio animadas.
2. **Pista instrumental** (MP3 320 kbps) sin voz, opcionalmente **transpuesta** en semitonos.

## Cómo funciona
| Paso | Herramienta |
|---|---|
| Quitar la voz | Demucs `htdemucs` (IA de separación de fuentes) |
| Letra con tiempos (voz → texto) | Whisper (`faster-whisper`) con marcas de tiempo por palabra |
| Detección de tonalidad | Krumhansl-Schmuckler sobre cromagrama (librosa) |
| Transposición sin cambiar tempo | librosa pitch shift |
| Vídeo | ffmpeg (incluido vía `imageio-ffmpeg`) + subtítulos ASS `\kf` |

La tonalidad se muestra en **notación americana** (C, C#, Db, D… y `m` para menor), p. ej. `Am → Bm (+2 st)`. Los archivos transpuestos llevan el tono en el nombre: `cancion_karaoke_Bm.mp4`.

## Instalación (Windows)
1. Instale **Python 3.10–3.12** desde python.org (marque *Add to PATH*).
2. Doble clic en `instalar.bat` (para GPU NVIDIA, edite la línea de torch indicada).
3. Doble clic en `KaraokeEasy.bat`.

Opcional: `build_exe.bat` crea `dist\KaraokeEasy\KaraokeEasy.exe` con PyInstaller.

> La primera ejecución descarga los modelos (Demucs ~80 MB, Whisper `small` ~460 MB).

## Uso
1. **Buscar…** y elija el archivo.
2. **Analizar tono** → muestra la tonalidad original.
3. Ajuste **Transponer (semitonos)**: verá el nuevo tono en vivo.
4. Elija modelo de Whisper (`medium`/`large-v3` = letra más precisa, más lento) e idioma.
5. **Crear karaoke**. Los resultados quedan en `<salida>\<canción>_karaoke\`.

### Corregir la letra
Si Whisper se equivoca, edite `_trabajo\letra.json` (texto y tiempos) y vuelva a pulsar *Crear karaoke*: reutiliza la separación y la letra, y solo regenera el vídeo (también sirve para sacar otras versiones de tono rápido).

### Línea de comandos
```
python cli.py "mi cancion.mp3" -o salida -s -2 -m medium -l es
```
