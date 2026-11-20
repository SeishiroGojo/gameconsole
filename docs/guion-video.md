# Guion del video de demostración (máximo 15 min)

**Preparación (antes de grabar)**
1. `docker compose up -d --build --wait` y abrir http://localhost:8000 en **dos pestañas** (consola en una, **#panel** en la otra, lado a lado si se puede).
2. Tener a mano VS Code con: `prolog/connect4_ai.pl`, `console/app/games/base.py`, `console/app/events.py`, y GitHub Actions del repo.
3. Grabar con OBS (o el grabador de la barra de Xbox con la ventana del navegador). Subir a YouTube como **No listado** y pegar el enlace en el README.

| Min | Quién | Qué decir | Qué mostrar |
|---|---|---|---|
| 0:00–1:00 | Emerson | Presentación: GameConsole, tres juegos POO, IA en Prolog, panel conectado a GameStats | README con el diagrama |
| 1:00–3:00 | Emerson | Arquitectura: navegador → consola FastAPI → Prolog / GameStats (Go ingesta, Scala analiza). La consola no calcula estadísticas | Diagrama del README + `docker compose ps` |
| 3:00–6:30 | Emerson | **Los tres juegos.** Conecta 4 (jugar 3 jugadas, mostrar el cuadro "Prolog eligió…"), 2048 con flechas, Buscaminas (primera jugada segura, bandera) | Pestaña Consola |
| 6:30–8:30 | Kendall | **Concurrencia.** Crear 3–4 partidas a la vez en la misma página y otra en una segunda pestaña. Pulsar **Demostración → Lanzar (3 por juego)** y pasar al Panel para ver subir y bajar "en curso". Cada tarjeta muestra su identificador. Explicar: una cola y una tarea por partida; `publish` no espera a la red | Dos pestañas; `events.py` (clase `EventPublisher`) |
| 8:30–11:00 | Kendall | **Prolog.** Mostrar `connect4_ai.pl`: negamax + alfa-beta + heurística. Probar: dejar tres fichas en línea y ver que la IA bloquea. Mostrar un evento `AI_DECISION` (estado, columna, puntaje, nodos) | `connect4_ai.pl`, `test_ai.pl` (8 pruebas), `curl` o la caja de la IA |
| 11:00–13:00 | Kendall | **Panel con GameStats.** Panel abierto mientras se juega: "en curso" sube y baja, iniciadas por juego, estadísticas generales vs por juego. Terminar una partida y ver cómo cambian victorias/derrotas. Explicar que vienen de `/stats/live`, `/stats/games` y `/stats/overall` | Pestaña Panel + juego al lado |
| 13:00–14:30 | Emerson | **Docker, CI/CD, deployment.** Dockerfiles, compose, pipeline verde (tests → integración → publicar), `docker-compose.deploy.yml` con imágenes de GHCR | GitHub Actions, carpeta del repo |
| 14:30–15:00 | Ambos | Cierre: decisiones técnicas (POO, Prolog, tolerancia a fallos) y qué aprendieron | README / docs |

**Truco para mostrar tolerancia a fallos (opcional, 30 s):** `docker compose stop prolog` → jugar una ficha → sale "Prolog no respondió" → `docker compose start prolog` → *Reintentar jugada de la IA*.

**Si algo falla en la grabación:** `docker compose logs console` y `docker compose restart console`.
