# Karaoke Easy 🎤

Programa para Windows que convierte una canción (**MP4, MP3, WAV**, también M4A/FLAC/MKV/MOV, o **un enlace de YouTube** u otro sitio compatible con yt-dlp) en:

1. **Vídeo karaoke único** (MP4 1080p): letra sincronizada palabra por palabra con relleno de color, fondo generado a partir del nombre de la canción (colores/formas distintas para cada tema) o el vídeo original difuminado, y ondas de audio animadas.
2. **Cuenta atrás con puntitos** (● ● ● ●) que se rellenan en la intro y en pausas largas sin voz, para saber cuándo entrar.
3. **Voz guía activable en cualquier momento**: el MP4 trae 2 pistas de audio, *Karaoke (sin voz)* y *Con voz guía*; se cambia en vivo desde el reproductor (VLC: tecla **B**; Reproductor multimedia de Windows: **⋯ › Idioma de audio**). También se exporta `_con_voz.mp3`.
4. **Pista instrumental** (MP3 320 kbps) sin voz, opcionalmente **transpuesta** en semitonos.

## Cómo funciona
| Paso | Herramienta |
|---|---|
| Quitar la voz | Demucs `htdemucs` (IA de separación de fuentes) |
| Letra correcta | LRCLIB (o pegada a mano); si no hay, Whisper |
| Ritmo | Pulso y compás (librosa): cuenta atrás de 4 tiempos que acaba en la entrada de la voz; inicios de palabra cuadrados al ataque de la voz o a la semicorchea más cercana (< 80 ms) |
| Sincronización por palabra | Whisper (ventana de cada verso) + alineación forzada MMS_FA (CTC) recortada a la voz real |
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
La letra correcta se obtiene de [LRCLIB](https://lrclib.net) (o se pega en el cuadro *Letra*) y se alinea con la voz usando los tiempos de Whisper. Para ajustar tiempos a mano, copie `_trabajo\letra.json` a `_trabajo\letra_manual.json`, edítelo y vuelva a pulsar *Crear karaoke*: reutiliza la separación y la letra, y solo regenera el vídeo (también sirve para sacar otras versiones de tono rápido).

### Línea de comandos
```
python cli.py "mi cancion.mp3" -o salida -s -2 -m medium -l es
```

## Instalador para usuarios finales (modelos incluidos)
GitHub Actions (`.github/workflows/windows-installer.yml`) construye en Windows un **`KaraokeEasy-Setup-x.y.z.exe`** que ya trae dentro Demucs `htdemucs`, Whisper `small` y el alineador MMS_FA: el usuario solo hace *Siguiente → Instalar*, abre el programa y procesa **sin internet ni Python**.

- Descarga: pestaña *Actions* → último run → artefacto **KaraokeEasy-Setup**. Al crear un tag `v1.0.0` se publica también como *Release*.
- Construcción local: `instalar.bat` y luego `build_exe.bat` (requiere Inno Setup 6).

## Pruebas
`python -m pytest tests` (tonalidades, transposición, tiempos karaoke, cuenta atrás, render con 2 pistas). En CI además se ejecuta el `.exe` empaquetado sin internet sobre una canción de prueba con voz sintética de Windows y se verifica que separe, transcriba y genere los archivos.

## Desde un enlace
Pegue el enlace (YouTube u otro sitio compatible con [yt-dlp](https://github.com/yt-dlp/yt-dlp)) en el campo *Archivo o enlace* y pulse **Crear karaoke**: se descarga en `<salida>\descargas\` y se procesa igual que un archivo. El artista y el título del vídeo se usan para buscar la letra. Descargue solo contenido sobre el que tenga derechos o permiso.

## Integración continua
- **Pruebas rápidas** (`tests.yml`, Linux, ~2 min): en cada push.
- **Instalador + Release** (`windows-installer.yml`, Windows, ~8–10 min): solo al cambiar el número en `VERSION` (o con un tag `v*`, o a mano desde *Actions → Run workflow*). Publica la Release `v<VERSION>` con el `Setup.exe`.
