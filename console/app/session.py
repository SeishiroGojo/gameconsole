"""Una partida en ejecución: une el juego, el envío de eventos y la IA de Prolog.

``GameSession`` es la única clase que conoce a la vez al juego, a GameStats y a
Prolog. Los juegos no saben nada de eso.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Optional

from .events import EventPublisher, to_gamestats_event, utc_now_iso
from .games.base import Game, GameEvent, InvalidAction, Outcome
from .prolog_client import PrologClient, PrologUnavailable


class GameSession:
    """Instancia de juego: cada una tiene un ``match_id`` único."""

    def __init__(self, game: Game, publisher: EventPublisher, prolog: Optional[PrologClient]) -> None:
        self.game = game
        self.match_id = f"{game.game_id}-{uuid.uuid4()}"
        self._publisher = publisher
        self._prolog = prolog
        self._lock = asyncio.Lock()  # serializa las acciones de ESTA partida
        self._started_mono = time.monotonic()
        self._last_activity = time.monotonic()
        self._closed = False
        self.started_at = utc_now_iso()
        self.finished_at: Optional[str] = None
        self.ai_error: Optional[str] = None

    # ----------------------------------------------------------------- ciclo

    def start(self) -> None:
        self._emit(self.game.start_events())

    async def act(self, action: dict[str, Any]) -> None:
        """Aplica una acción de la persona y, si corresponde, deja jugar a la IA."""
        async with self._lock:
            self._touch()
            self._emit(self.game.apply(action))
            self._close_if_over()
            if self.game.awaiting_ai:
                await self._run_ai()

    async def retry_ai(self) -> None:
        """Reintenta la jugada de la computadora (si Prolog falló antes)."""
        async with self._lock:
            self._touch()
            if not self.game.awaiting_ai:
                raise InvalidAction("la computadora no tiene un turno pendiente")
            await self._run_ai()

    async def abandon(self) -> None:
        async with self._lock:
            if self.game.is_over:
                return
            self.game.abandon()
            self._close_if_over()

    # ------------------------------------------------------------- consulta

    @property
    def is_over(self) -> bool:
        return self.game.is_over

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_activity

    def describe(self) -> dict[str, Any]:
        outcome = self.game.outcome
        return {
            "matchId": self.match_id,
            "gameId": self.game.game_id,
            "title": self.game.title,
            "status": "finished" if self.game.is_over else "playing",
            "outcome": outcome.value if outcome else None,
            "moves": self.game.moves,
            "score": self.game.score,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "aiError": self.ai_error,
            "state": self.game.view(),
        }

    # -------------------------------------------------------------- internos

    def _touch(self) -> None:
        self._last_activity = time.monotonic()

    async def _run_ai(self) -> None:
        """Consulta a Prolog y aplica su respuesta. Si falla, la partida sigue pendiente."""
        if self._prolog is None:
            self.ai_error = "El servicio Prolog no está configurado"
            raise PrologUnavailable(self.ai_error)
        request = self.game.ai_request()  # type: ignore[attr-defined]
        try:
            decision, latency_ms = await self._prolog.best_move(request)
        except PrologUnavailable as exc:
            self.ai_error = str(exc)
            raise
        self.ai_error = None
        self._emit(self.game.apply_ai(decision, latency_ms))  # type: ignore[attr-defined]
        self._close_if_over()

    def _emit(self, events: list[GameEvent]) -> None:
        if self._closed or not events:
            return
        wrapped = [
            to_gamestats_event(
                e,
                game_id=self.game.game_id,
                game_version=self.game.version,
                match_id=self.match_id,
            )
            for e in events
        ]
        self._publisher.publish(self.match_id, wrapped)

    def _close_if_over(self) -> None:
        """Si la partida terminó, envía los eventos de cierre (una sola vez)."""
        if self._closed or not self.game.is_over:
            return
        duration_ms = int((time.monotonic() - self._started_mono) * 1000)
        self._emit(self.game.closing_events(duration_ms))
        self._closed = True
        self.finished_at = utc_now_iso()
