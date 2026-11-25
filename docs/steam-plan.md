# Plan Steam y roadmap de modos de juego
Última actualización: 2026-11-25 · Responsable: PO · Estado: borrador. Los requisitos de Valve están sin verificar: confirmar en partner.steamgames.com.

## 1. Cómo se publica en Steam (proceso)
| Paso | Qué es | Quién |
|---|---|---|
| 1 | Cuenta en Steamworks: datos fiscales y bancarios, verificación de identidad | Dueño |
| 2 | Pago de Steam Direct: **USD 100 por aplicación**. Desde el pago hay **30 días de espera** antes de poder lanzar | Dueño |
| 3 | Ficha de tienda: capturas, video, descripción, etiquetas, categoría **Software** | PO + dev |
| 4 | Encuesta de contenido: declarar el uso de IA (ver 2) | Dueño |
| 5 | Ficha "Próximamente" pública **al menos 2 semanas** antes del lanzamiento; Valve la revisa antes (unos días) | Valve |
| 6 | Subir el build con SteamPipe (`steamcmd`, automatizable en el CI) | Dev |
| 7 | Revisión del build por Valve (unos días) → lanzamiento | Valve |

Lo más corto posible: unas **5–6 semanas** desde el pago hasta el lanzamiento. Se usan para medir los deseados.

## 2. Riesgos de Valve
- **Declaración de IA:** desde enero de 2026, Valve pide declarar el contenido generado por IA que consume el jugador.
  - Nuestra IA separa la voz y sincroniza la letra con la canción del propio usuario; no genera contenido nuevo.
  - Hay que declararlo con transparencia y explicar las salvaguardas. Por confirmar si cuenta como "generado en vivo".
- **Derechos de autor:** la versión de Steam **no descarga de YouTube**. Solo archivos propios, con aviso de responsabilidad en los términos de uso.
- **Aceptación de la categoría:** no se encontraron casos claros de apps parecidas en Steam. Conviene preguntar al soporte de Steamworks antes de invertir más allá de los USD 100.

## 3. Cambios técnicos para la versión Steam
1. **Licencia:** Steam reemplaza a Lemon Squeezy en esta versión. Si la cuenta de Steam tiene el producto, la app funciona. El módulo `license.py` tendrá un modo "steam".
2. **Actualizaciones:** las entrega Steam. Se desactiva el actualizador propio en esta versión.
3. **SDK de Steamworks:** integrado en la app de Tauri (crate `steamworks-rs`). Da logros, superposición de Steam, Remote Play y nube.
4. **Build:** el CI genera además una versión Steam (sin descarga de YouTube ni instalador) y la sube con SteamPipe a la rama "beta".
5. **Nube de Steam:** guarda favoritos, listas y ajustes. Las canciones no, por tamaño y por derechos.

## 4. Roadmap de modos de juego (con condiciones para avanzar)
Cada etapa solo empieza si se cumple la condición de la anterior. Sin condición cumplida, no se invierte.

### AHORA: lanzamiento local (fiesta en casa) · USD 14,99
- Modo fiesta, puntuación, segunda pantalla: **ya existen**.
- **Teléfono como micrófono:** la app muestra un código QR, el teléfono abre una página local y envía la voz por wifi.
- **Duelo por turnos:** 2 a 8 jugadores, ranking al final de la ronda.
- **Logros de Steam:** primera canción, 90 % de afinación, 10 canciones en una fiesta…
- **Aceleración GPU:** procesar en 20–30 s en vez de 5 min.
- **Condición para avanzar:** 5.000 deseados antes del lanzamiento y **500 ventas en los 3 primeros meses** con reseñas de 80 % o más positivas.

### SIGUIENTE: "online" con poco desarrollo
- **Remote Play Together:** amigos en otra casa se unen a la fiesta por Steam sin tener el juego. Valve transmite imagen y sonido, y no hay que programar la red. Solo requiere probar latencia y micrófono.
- **Duelo a la vez:** 2 voces simultáneas, cada una con su línea de notas en pantalla dividida.
- **Ranking por canción entre amigos:** el puntaje se asocia a una huella de la canción, sin subir el audio.
- **Condición para avanzar:** 2.000 ventas y que un 20 % o más de las sesiones use Remote Play o duelo. Sin telemetría, se mide con encuestas en la comunidad y con el dato de Steam.

### DESPUÉS: online de verdad (solo si va muy bien)
- **Salas online:** cada jugador tiene la canción en su PC (la importa con el `.karaoke` o la procesa él). Se sincroniza solo la reproducción y la puntuación, **nunca el audio de la canción**: así no distribuimos música.
- **Torneos y temporadas:** ranking global por canción, sin subir el audio.
- **Modo espectador para streamers:** una vista limpia para OBS y votaciones del chat.
- **Costo:** servidores de partidas o sesiones P2P de Steam (Steam Networking evita servidores propios), anticheat básico de puntajes y moderación.
- **Condición para empezar:** 10.000 ventas o ingresos que paguen 6 meses de desarrollo y servidores.

## 5. Próximos pasos
1. Dueño: crear la cuenta de Steamworks y pagar Steam Direct.
2. PO: texto de la ficha + guion del video del modo fiesta.
3. Dev: modo de licencia "steam" + versión del build sin YouTube.
4. Dev: teléfono como micrófono (el diferencial más visible en el video).
