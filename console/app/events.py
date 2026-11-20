"""Eventos compatibles con GameStats y envío concurrente, sin bloquear el juego.

Contrato (docs/event-spec.md de GameStats):
    eventId, timestamp, gameId, gameVersion, matchId, playerId, type, action, data

Estrategia de envío (resumen en docs/decisiones-tecnicas.md):

* Cada partida tiene su propia cola y su propia tarea (``asyncio``). Una
  partida lenta o con GameStats caído no frena a las demás ni a la interfaz.
* Dentro de una partida los eventos salen en orden (una sola tarea consume la
  cola), y se agrupan en lotes: GameStats acepta arreglos en POST /events.
* ``publish`` NUNCA espera a la red: solo encola y vuelve de inmediato.
* Si el envío falla (red o 5xx) se reintenta con espera exponencial. Es seguro
  reintentar porque GameStats ignora los eventos repetidos (mismo eventId).
* Si se agotan los reintentos, el lote se descarta y se registra (contador
  ``dropped``); la partida nunca se interrumpe por esto.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from .config import Settings
from .games.base import GameEvent

log = logging.getLogger("gameconsole.events")

BATCH_SIZE = 25


def utc_now_iso() -> str:
    """Instante actual en UTC, formato RFC 3339 con milisegundos (ej. 2026-11-10T15:00:00.123Z)."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def to_gamestats_event(
    event: GameEvent, *, game_id: str, game_version: str, match_id: str, timestamp: Optional[str] = None
) -> dict[str, Any]:
    """Convierte un hecho de dominio en un evento con la estructura de GameStats."""
    body: dict[str, Any] = {
        "eventId": str(uuid.uuid4()),
        "timestamp": timestamp or utc_now_iso(),
        "gameId": game_id,
        "gameVersion": game_version,
        "matchId": match_id,
        "type": event.type,
    }
    if event.player_id:
        body["playerId"] = event.player_id
    if event.action:
        body["action"] = event.action
    if event.data:
        body["data"] = event.data
    return body


class EventPublisher:
    """Envía eventos a GameStats en segundo plano, una cola por partida."""

    def __init__(self, settings: Settings, client: Optional[httpx.AsyncClient] = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.publish_timeout_seconds)
        self._owns_client = client is None
        self._queues: dict[str, asyncio.Queue] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        # Contadores para el panel de estado y para las pruebas.
        self.published = 0  # eventos entregados (aceptados por GameStats)
        self.retries = 0  # reintentos realizados
        self.dropped = 0  # eventos descartados tras agotar los reintentos
        self.rejected = 0  # eventos que GameStats rechazó por inválidos (no se reintentan)

    # ------------------------------------------------------------------ API

    def publish(self, match_id: str, events: list[dict[str, Any]]) -> None:
        """Encola eventos de una partida. No espera a la red."""
        if not events:
            return
        queue = self._queues.get(match_id)
        if queue is None:
            queue = asyncio.Queue()
            self._queues[match_id] = queue
            self._tasks[match_id] = asyncio.create_task(self._consume(match_id, queue))
        for e in events:
            queue.put_nowait(e)

    @property
    def pending(self) -> int:
        """Eventos que todavía esperan ser enviados (suma de todas las partidas)."""
        return sum(q.qsize() for q in self._queues.values())

    @property
    def active_matches(self) -> int:
        return len(self._queues)

    def stats(self) -> dict[str, int]:
        return {
            "published": self.published,
            "pending": self.pending,
            "retries": self.retries,
            "dropped": self.dropped,
            "rejected": self.rejected,
            "activeQueues": self.active_matches,
        }

    async def flush(self, timeout: float = 10.0) -> None:
        """Espera a que se vacíen todas las colas (para pruebas y para el cierre ordenado)."""
        tasks = list(self._tasks.values())
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout)

    async def close(self) -> None:
        try:
            await self.flush(timeout=5.0)
        except asyncio.TimeoutError:
            for t in self._tasks.values():
                t.cancel()
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------- internos

    async def _consume(self, match_id: str, queue: asyncio.Queue) -> None:
        """Tarea de una partida: toma lotes de la cola y los envía en orden."""
        try:
            while True:
                try:
                    first = await asyncio.wait_for(queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    # Cola vacía: la tarea termina; publish() creará otra si hace falta.
                    if queue.empty():
                        break
                    continue
                batch = [first]
                while len(batch) < BATCH_SIZE and not queue.empty():
                    batch.append(queue.get_nowait())
                await self._send_with_retry(match_id, batch)
                if any(e["type"] == "MATCH_FINISHED" for e in batch) and queue.empty():
                    break
        finally:
            # Registrar la salida solo si nadie encoló algo mientras tanto.
            if self._queues.get(match_id) is queue and queue.empty():
                self._queues.pop(match_id, None)
                self._tasks.pop(match_id, None)
            elif self._queues.get(match_id) is queue:
                # Llegaron eventos justo al terminar: se continúa con una tarea nueva.
                self._tasks[match_id] = asyncio.create_task(self._consume(match_id, queue))

    async def _send_with_retry(self, match_id: str, batch: list[dict[str, Any]]) -> None:
        s = self._settings
        delay = s.publish_backoff_seconds
        url = f"{s.ingest_url}/events"
        for attempt in range(1, s.publish_max_attempts + 1):
            try:
                resp = await self._client.post(url, json=batch)
            except httpx.HTTPError as exc:
                log.warning("partida %s: fallo de red al enviar %d eventos (intento %d): %s",
                            match_id, len(batch), attempt, exc)
            else:
                if resp.status_code in (200, 202):
                    self.published += len(batch)
                    return
                if resp.status_code == 207:
                    # GameStats aceptó algunos y rechazó otros por inválidos: reintentar no sirve.
                    bad = len((resp.json() or {}).get("rejected") or [])
                    self.rejected += bad
                    self.published += len(batch) - bad
                    log.error("partida %s: GameStats rechazó %d evento(s): %s", match_id, bad, resp.text[:300])
                    return
                if 400 <= resp.status_code < 500:
                    self.rejected += len(batch)
                    log.error("partida %s: GameStats respondió %d (no se reintenta): %s",
                              match_id, resp.status_code, resp.text[:300])
                    return
                log.warning("partida %s: GameStats respondió %d (intento %d)", match_id, resp.status_code, attempt)

            if attempt < s.publish_max_attempts:
                self.retries += 1
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8.0)

        self.dropped += len(batch)
        log.error("partida %s: se descartaron %d evento(s) tras %d intentos", match_id, len(batch), s.publish_max_attempts)
