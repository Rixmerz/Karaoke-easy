# Product context
Last updated: 2026-11-25

## Product
- Name: Karaoke Easy [repo]
- One-line description: App de Windows para practicar canto con cualquier canción: quita la voz, sincroniza la letra, cambia tono y velocidad, repite tramos y puntúa la afinación [repo]
- Stage: idea (producto funcional, sin usuarios) [user, 2026-11]
- Business model: canal principal Steam, pago único (uso personal y en clase); venta directa de la licencia anual Eventos para uso comercial [decisión PO, 2026-11-25]
- Pricing: Steam USD 14,99 (10 % de descuento de lanzamiento; precio por país de Valve); Eventos USD 249/año por venta directa [decisión PO, 2026-11-25]

## Context profile
- Customer type: B2C profesional (profesor de canto independiente) [decisión PO]
- Number of customers: 0 [user, 2026-11]
- Average ticket: Unknown
- Frequency of use: hipótesis semanal (en cada clase)
- Platform: escritorio Windows; el procesamiento corre en el PC del usuario (sin coste de servidores salvo licencias) [repo]
- Regulation: derechos de autor de música y letras; condiciones de uso de YouTube

## Users and customers
- Primary segment: fiestas en casa y jugadores en Steam; profesores de canto como segmento de marketing [decisión PO, 2026-11-25]
- Other segments: alumnos (usan, no pagan); organizadores de eventos y bares (más adelante)
- Buyer vs user: paga el profesor
- Non-target users (por ahora): eventos y bares, porque exigen licencias de reproducción pública, soporte en vivo y otra venta
- Top problems (hipótesis, sin validar): pista sin voz de cualquier canción; ponerla en el tono del alumno; practicar un tramo lento y en bucle; medir la afinación

## Market
- Competitors: Unknown (por investigar)
- Alternatives: versiones karaoke en YouTube, webs gratuitas para quitar la voz, tocar el piano en clase

## Goals and metrics
- Primary outcome metric (propuesta): profesores activos que usan la app en ≥2 clases por semana
- Baselines: 0 (2026-11)

## Constraints
- Equipo: una persona trabajando con IA [user]
- Técnicas: separar la voz es lento sin GPU (~5 min por canción en CPU)
- Legales: descarga desde YouTube; letras de LRCLIB; licencia del modelo de sincronía MMS (posiblemente no comercial, por verificar); ffmpeg GPL incluido
- Repo: pasa a privado antes de vender [user]

## Conventions
- Artifact language: español
- Decision log: docs/decisiones.md
- Scoring model, cycle, goal system: None; use the agent's defaults

## Open questions
- ¿Cuánto pagaría un profesor al año?
- ¿Dan clase presencial u online? ¿Usan Windows?
- ¿El modelo MMS permite uso comercial?
