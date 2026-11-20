"""Registro de las partidas (instancias) que están en ejecución en esta consola."""

from __future__ import annotations

from typing import Any, Optional

from .config import Settings
from .events import EventPublisher
from .games import GAME_CLASSES, InvalidAction
from .prolog_client import PrologClient
from .session import GameSession


class UnknownGame(Exception):
    pass


class MatchRegistry:
    def __init__(self, settings: Settings, publisher: EventPublisher, prolog: Optional[PrologClient]) -> None:
        self._settings = settings
        self._publisher = publisher
        self._prolog = prolog
        self._sessions: dict[str, GameSession] = {}

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {"gameId": c.game_id, "title": c.title, "description": c.description, "mode": c.mode, "version": c.version}
            for c in GAME_CLASSES.values()
        ]

    def create(self, game_id: str, options: Optional[dict[str, Any]] = None, player_id: str = "player") -> GameSession:
        cls = GAME_CLASSES.get(game_id)
        if cls is None:
            raise UnknownGame(game_id)
        game = cls(player_id=player_id, options=options)  # puede lanzar InvalidAction (opciones inválidas)
        session = GameSession(game, self._publisher, self._prolog)
        self._sessions[session.match_id] = session
        session.start()
        return session

    def get(self, match_id: str) -> Optional[GameSession]:
        return self._sessions.get(match_id)

    def all(self) -> list[GameSession]:
        return list(self._sessions.values())

    def summary(self) -> dict[str, Any]:
        """Instancias en esta consola (información operativa, NO son las estadísticas de GameStats)."""
        by_game: dict[str, dict[str, int]] = {gid: {"playing": 0, "finished": 0} for gid in GAME_CLASSES}
        for s in self._sessions.values():
            by_game[s.game.game_id]["finished" if s.is_over else "playing"] += 1
        return {"byGame": by_game, "total": len(self._sessions)}

    async def reap_once(self) -> dict[str, int]:
        """Abandona las partidas inactivas y olvida las terminadas hace tiempo."""
        abandoned = removed = 0
        for match_id, s in list(self._sessions.items()):
            if not s.is_over and s.idle_seconds > self._settings.idle_timeout_seconds:
                await s.abandon()
                abandoned += 1
            elif s.is_over and s.idle_seconds > self._settings.finished_retention_seconds:
                del self._sessions[match_id]
                removed += 1
        return {"abandoned": abandoned, "removed": removed}
