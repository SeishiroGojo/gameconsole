"""Partidas automáticas de demostración.

Sirven para mostrar la ejecución concurrente sin tener que jugar a mano: cada
"bot" crea una instancia real (con su propio matchId) y la juega paso a paso
usando exactamente la misma ruta que una persona (``GameSession.act``), de modo
que genera los mismos eventos y consulta a Prolog igual que en una partida normal.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import random
from typing import Optional

from .config import Settings
from .games import InvalidAction
from .prolog_client import PrologUnavailable
from .registry import MatchRegistry
from .session import GameSession

log = logging.getLogger("gameconsole.bots")

#: Jugadas máximas antes de abandonar (evita bots eternos en 2048 / Buscaminas).
MAX_ACTIONS = {"connect4": 40, "game-2048": 60, "minesweeper": 25}


class BotLauncher:
    def __init__(self, settings: Settings, registry: MatchRegistry) -> None:
        self._settings = settings
        self._registry = registry
        self._tasks: set[asyncio.Task] = set()
        self._counter = itertools.count(1)

    @property
    def running(self) -> int:
        return len(self._tasks)

    def launch(self, per_game: int) -> list[str]:
        """Crea ``per_game`` partidas de cada juego. Devuelve sus matchId."""
        wanted = per_game * 3
        if self.running + wanted > self._settings.bot_max_concurrent:
            return []
        ids: list[str] = []
        for game_id in ("connect4", "game-2048", "minesweeper"):
            for _ in range(per_game):
                n = next(self._counter)
                options = {"difficulty": random.choice(["easy", "medium"])} if game_id == "connect4" else {}
                session = self._registry.create(game_id, options, player_id=f"bot-{n}")
                ids.append(session.match_id)
                task = asyncio.create_task(self._play(session, random.Random(n)))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        return ids

    def cancel_all(self) -> None:
        for t in list(self._tasks):
            t.cancel()

    async def _play(self, session: GameSession, rng: random.Random) -> None:
        game_id = session.game.game_id
        delay = self._settings.bot_delay_seconds
        try:
            for _ in range(MAX_ACTIONS[game_id]):
                if session.is_over:
                    return
                await asyncio.sleep(delay * rng.uniform(0.5, 1.5))
                await self._one_move(session, rng)
            await session.abandon()
        except asyncio.CancelledError:
            raise
        except Exception:  # un bot que falla no debe tumbar nada
            log.exception("el bot de %s falló", session.match_id)
            await session.abandon()

    async def _one_move(self, session: GameSession, rng: random.Random) -> None:
        view = session.game.view()
        game_id = session.game.game_id
        if game_id == "connect4":
            legal = [c for c in range(view["cols"]) if view["board"][0][c] == 0]
            action = {"type": "drop", "column": rng.choice(legal)}
        elif game_id == "game-2048":
            action = {"type": "move", "direction": rng.choice(["up", "down", "left", "right"])}
        else:
            hidden = [(r, c) for r, row in enumerate(view["cells"]) for c, cell in enumerate(row) if cell["s"] == "hidden"]
            r, c = rng.choice(hidden)
            action = {"type": "reveal", "row": r, "col": c}
        try:
            await session.act(action)
        except InvalidAction:
            pass  # p. ej. un movimiento de 2048 que no cambia nada: se intenta otro en el siguiente turno
        except PrologUnavailable:
            await asyncio.sleep(1.0)  # Prolog no respondió: se reintenta la jugada de la IA
            try:
                await session.retry_ai()
            except (PrologUnavailable, InvalidAction):
                pass
