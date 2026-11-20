# Decisiones técnicas

## 1. Programación orientada a objetos (los tres juegos)

```
Game (clase abstracta)            GameSession
 ├─ Connect4Game                   une un Game + el envío de eventos + Prolog
 ├─ Game2048
 └─ MinesweeperGame
```

* **Abstracción.** `Game` define el contrato: `start_data()`, `apply(acción)`, `view()` y el cierre de partida. La consola solo conoce `Game`; no sabe nada de fichas, tiles o minas.
* **Encapsulación.** El estado de cada juego es privado (`_board`, `_mines`, …) y solo cambia mediante `apply`. Hacia afuera solo sale `view()`, que **oculta las minas** mientras la partida sigue.
* **Polimorfismo.** `GameSession` trata igual a los tres juegos; agregar un cuarto solo exige otra subclase.
* **Plantilla de método.** `Game.closing_events()` arma `PLAYER_WON/LOST` y `MATCH_FINISHED` para todos; cada juego solo agrega detalles con `extra_finish_data()`.
* **Separación de responsabilidades.** Los juegos devuelven *hechos de dominio* (`GameEvent`); no conocen HTTP, GameStats ni Prolog. Convertirlos al formato de GameStats lo hace `events.py`.

## 2. Inteligencia en Prolog

`prolog/connect4_ai.pl` + `prolog/server.pl` (servicio HTTP independiente, `POST /move`).

1. Python envía el tablero (`board` 6×7, `player`, `depth`).
2. Prolog lo convierte a columnas y busca con **negamax con poda alfa-beta** (variante de minimax) hasta la profundidad pedida.
3. Evalúa con una **heurística de ventanas de 4 casillas** (tres propias + hueco = +50; tres del rival + hueco = −60; control del centro).
4. Responde `{column, score, nodes, depth, candidates}` y Python aplica esa columna.

La computadora **nunca juega al azar**. Se verifica con pruebas: gana si puede, bloquea al rival, prefiere ganar a bloquear y abre por el centro. Cada decisión se registra como evento `AI_DECISION`.

## 3. Envío concurrente de eventos (`console/app/events.py`)

* **Una cola y una tarea (`asyncio`) por partida.** Una partida lenta no frena a las demás ni a la interfaz; dentro de una partida los eventos salen en orden.
* **`publish()` nunca espera a la red**: solo encola.
* **Lotes**: GameStats acepta arreglos en `POST /events`; se envían hasta 25 eventos juntos.
* **Fallos**: errores de red y respuestas 5xx se reintentan con espera exponencial (0,5 s → 8 s, 6 intentos). Los rechazos 4xx/207 no se reintentan. Si se agotan los intentos se descarta el lote y se cuenta (`dropped`); **la partida nunca se interrumpe**.
* **Identificación**: `matchId = <juego>-<uuid4>` único por instancia, y `eventId = uuid4` por evento.

### Ajustes hechos en GameStats para que esto sea seguro (v2)

* **Idempotencia por `eventId`**: reintentar no duplica eventos.
* **Partida cerrada**: un reintento tardío de `MATCH_FINISHED` (2 min) se ignora en vez de abrir una partida nueva de un solo evento.

## 4. Panel de control y estadísticas

El panel consulta (vía la consola, que solo reenvía) tres endpoints de GameStats cada 2 segundos:

| Endpoint | Servicio | Contenido |
|---|---|---|
| `GET /stats/live` | Go (ingestión) | Por juego: instancias **iniciadas / en curso / terminadas** y eventos por tipo. Se actualiza con cada evento, sin esperar al fin de la partida |
| `GET /stats/games` | Scala (análisis) | Por juego: partidas, victorias, derrotas, empates, tasa de victoria, duración y jugadas medias, puntaje |
| `GET /stats/overall` | Scala (análisis) | Totales de todos los juegos |

Scala calcula todo con **funciones puras** sobre los eventos (`MatchSummaries.summarize` y `Aggregates.byGame/overall`), con pruebas unitarias.

**¿Por qué pasa por la consola y no desde el navegador?** Evita CORS y no obliga a exponer los puertos de GameStats. La consola no transforma los datos.

## 5. Tolerancia a fallos

| Falla | Comportamiento |
|---|---|
| GameStats caído | Las partidas siguen; los eventos se reintentan; el panel muestra un aviso |
| Prolog caído | La jugada de la persona queda registrada y aparece *Reintentar jugada de la IA* |
| Pestaña cerrada | A los 3 min sin actividad la partida se abandona (`MATCH_FINISHED` con `ABANDONED`) para que no quede "en curso" |
| Cierre de la consola | Se abandonan las partidas abiertas y se vacían las colas |
