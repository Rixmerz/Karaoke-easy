# Teléfono como micrófono

## Para el usuario

1. Conecta el teléfono al **mismo wifi** que el PC.
2. En el reproductor, toca **Teléfono** (junto a *Micrófono*). Aparece un código QR.
3. Escanéalo con la cámara del teléfono.
4. **Solo la primera vez**, el navegador avisa que "la conexión no es privada":
   - Android (Chrome): *Configuración avanzada → Continuar a … (no seguro)*.
   - iPhone (Safari): *Mostrar detalles → visitar este sitio web*.
   Es normal: el teléfono habla directo con tu PC, sin pasar por internet.
5. Toca **Empezar** y permite el micrófono. Tu voz sale por los parlantes del PC, con el eco
   y el volumen de siempre, y cuenta para la puntuación.

Hasta 4 teléfonos a la vez (duetos). Con varios, el selector junto a *Teléfono* elige cuál se
puntúa. En el **Duelo por turnos** cada jugador elige su micrófono (PC o Teléfono 1–4).

Si no conecta: revisa que ambos estén en el mismo wifi (no en la red de invitados, que suele
aislar los equipos) y que el firewall de Windows permita a Karaoke Easy en redes privadas.

## Por qué HTTPS con certificado propio

Los navegadores móviles solo permiten el micrófono en un contexto seguro (HTTPS), y el teléfono
llega al PC por su IP local, para la que ninguna autoridad emite certificados. Opciones:

| Opción | Problema |
|---|---|
| HTTP simple | `getUserMedia` está bloqueado: no funciona. |
| WebRTC | También necesita `getUserMedia`, es decir, HTTPS. No resuelve nada y añade señalización. |
| Certificado real para un dominio propio con DNS a la IP local (como `plex.direct`) | Sin advertencia, pero exige dominio, DNS dinámico y emitir/renovar certificados por instalación. Opción para más adelante. |
| App nativa para el teléfono | Sin advertencia, pero hay que publicar y mantener dos apps. |
| **HTTPS autofirmado (elegido)** | Una advertencia la primera vez por teléfono. Cero dependencias, funciona sin internet. |

El certificado (RSA 2048, 10 años) se crea con la biblioteca estándar de Python la primera vez
y se guarda en `%LOCALAPPDATA%\KaraokeEasy\telefono\`. Al reutilizarlo, el navegador recuerda la
excepción y no vuelve a avisar.

## Modelo de seguridad

- El servidor de la red local **solo existe mientras el teléfono está activo**; *Apagar
  teléfono* lo cierra y corta las conexiones. Se enlaza a la IP de la red local, no a todas.
- Cada sesión usa un **código de emparejamiento** aleatorio de 6 caracteres (dentro del QR).
  Sin él no se sirve ni la página ni el audio. Tras 20 intentos fallidos el código cambia.
- El teléfono solo puede **enviar** audio; no puede leer la biblioteca ni controlar el PC.
  La interfaz del PC recibe el audio por el servidor local (127.0.0.1), protegido por su token.
- Todo el tráfico va cifrado por TLS dentro de la red local; nada sale a internet.

## Detalles técnicos

- Teléfono: AudioWorklet → PCM 16 bits mono a 24 kHz, paquetes de 20 ms por WebSocket seguro.
  Si la red se atasca, descarta paquetes en vez de acumular retraso.
- PC: el motor reenvía los paquetes por un WebSocket local; un AudioWorklet los reproduce con un
  colchón de 40 ms (máximo 150 ms) y entra en la misma cadena que el micrófono del PC.
- Latencia estimada de punta a punta: 90–150 ms (captura del teléfono 20–40 ms, paquete 20 ms,
  wifi 5–30 ms, colchón 40 ms, salida del PC 10–30 ms). La puntuación tolera hasta 400 ms de
  atraso con micrófono de teléfono.
- Código: `karaoke_easy/phonemic.py`, `karaoke_easy/qr.py`, `ui/phone.html`.
