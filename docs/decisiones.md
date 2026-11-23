# Registro de decisiones de producto

## 2026-11-23 · Modelo de venta y primer segmento
**Decisión:** ejecutable de Windows con **licencia anual por profesor**, activada contra una base de datos online. Primer segmento: **profesores de canto**. Eventos y bares, más adelante.

**Por qué profesores primero:**
- La app ya tiene lo que usan en clase: cambio de tono, bucle A-B, velocidad, puntuación de afinación y grabación.
- Usarían la app cada semana, lo que justifica pagar cada año.
- El uso es educativo y privado, con menos riesgo legal que reproducir música en público.
- A los profesores se les llega uno a uno (escuelas, redes), un ritmo que una sola persona puede sostener.

**Por qué no eventos todavía:** pagan más, pero exigen licencias de música pública, soporte en directo y equipos variados. Se revisa cuando haya 20 profesores pagando.

**Por qué licencia anual y no suscripción mensual ni venta del código:** todo corre en el PC del usuario, así que no hay costo de servidores que justifique cobrar cada mes. La licencia anual paga las actualizaciones. Vender el código no protege el negocio.

**Cómo funciona la licencia:**
- Clave de licencia activada en hasta 2 equipos.
- La app vuelve a verificarla cada 7 días y funciona sin internet durante 14 días como margen.
- Una prueba gratis de 14 días sin clave.

**Requisitos antes de cobrar:**
1. Hacer privado el repositorio.
2. Verificar la licencia del modelo de sincronía MMS y cambiarlo si es no comercial.
3. Presentar la app como "practica con tus propias canciones"; el enlace de YouTube queda como responsabilidad del usuario.
4. Cumplir la GPL de ffmpeg: publicar o enlazar el código fuente de ffmpeg.

**Cómo sabremos si funciona:** 5 entrevistas con profesores, que confirmen el problema y den una disposición a pagar, y después 10 profesores en prueba gratis. Si menos de 3 de cada 10 pasan a pagar, se revisa el segmento.

## 2026-11-23 · Segmento eventos
**Decisión:** el mismo programa tendrá una **licencia "Eventos"**, más cara, con procesamiento en lote, motor con GPU, modo fiesta y segunda pantalla. Sale después de la versión para profesores.
**Condiciones:**
- Cada cliente procesa su propia música en su equipo.
- En la versión Eventos no se promociona la descarga desde YouTube.
- Los términos de uso dejan al cliente como responsable de los derechos y de la licencia de reproducción pública (SCD, SGAE, etc.).

## 2026-11-23 · DESCARTADO: biblioteca de canciones ya procesadas
**Opciones descartadas:** subir pistas procesadas a YouTube; vender una biblioteca de canciones; regalarla junto con el programa.
**Por qué:** la pista sin voz sale de la grabación original. Repartirla, cobrando o gratis, es distribuir copias de obras protegidas, y quien las distribuye es el responsable.
**Sí se permite:** canciones de dominio público, con licencia libre, propias o autorizadas por escrito.

## 2026-11-23 · Precios iniciales (hipótesis a validar en entrevistas)
**Referencias** (precios públicos, nov-2026, varían por región):
- Moises Pro: ~USD 96/año.
- LALAL.AI Pro: ~USD 180/año.
- Sight Singing Studio: USD 99.99/año.
- KaraFun Pro (uso comercial, incluye catálogo): USD 49/mes (~USD 588/año).

**Decisión:**
| Licencia | Precio | Incluye |
|---|---|---|
| Prueba | Gratis, 14 días | Todo |
| Profesor | **USD 79/año** (fundadores: USD 49 el primer año, primeros 20) | Todo menos lote masivo y modo eventos; 2 PCs |
| Eventos | **USD 249/año** | Lote ilimitado, GPU, modo fiesta, segunda pantalla; 2 PCs |

**Por qué:**
- Profesor va por debajo de LALAL.AI y en línea con Moises o Sight Singing, pero hace más para una clase: letra sincronizada, tono, bucle y puntuación.
- Eventos cuesta menos de la mitad que KaraFun Pro porque no incluye canciones.
- El costo por cliente es casi 0, porque todo se procesa en el PC del cliente.

**Validación:**
- En las 5 entrevistas, preguntar 4 precios: caro, barato, demasiado caro, demasiado barato.
- Si la mayoría ve USD 79 como "caro", bajar a USD 59.
- Precio regional para Latinoamérica (~40 % menos): se decide tras las entrevistas.

## 2026-11-23 · Actualizaciones, telemetría y API propia
**Problema detectado:** las actualizaciones y la descarga de modelos salen hoy de las Releases de GitHub de este repo (`app.py`, `downloads.py`, `server.py`). Si el repo pasa a privado, **dejan de funcionar** para los clientes.

**Decisión:**
1. **Actualizaciones:**
   - Se crea un repo **público solo de descargas** (`Rixmerz/karaoke-easy-releases`) que contiene únicamente instaladores y modelos, sin código.
   - El CI publica allí y la app consulta ese repo. Costo 0, y la actualización automática actual se mantiene.
   - Más adelante, el canal se puede mover a la API propia para separar beta y estable, o publicar por etapas.
2. **Telemetría:**
   - Mínima y **con permiso**: una casilla en el primer arranque, desactivada si el usuario no acepta.
   - Eventos anónimos: app abierta, canción creada (duración y tiempo de proceso), sesión de práctica (minutos, uso de tono, bucle y puntuación), errores del motor.
   - Nunca se envían títulos, archivos, letras ni audio.
   - Sirve para medir la métrica principal: profesores activos con 2 o más clases por semana.
3. **API propia (más adelante):** un Cloudflare Worker con base de datos D1 (nivel gratuito) con:
   - `/v1/events` para la telemetría;
   - `/v1/update` con el manifiesto de versiones y canales;
   - `/v1/errors` para reportes de fallos.
   - Las licencias las sigue gestionando Lemon Squeezy.

**Orden:**
- (a) Repo de descargas antes de privatizar.
- (b) Telemetría y API cuando haya los primeros usuarios en prueba: sin usuarios no hay nada que medir.
