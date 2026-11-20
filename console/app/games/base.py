"""Clase base abstracta de los juegos de la consola.

Cada juego es una subclase de :class:`Game`. La clase base define el
*contrato* (qué debe saber hacer cualquier juego) y el ciclo de vida común
(iniciar, jugar, terminar), y deja a las subclases únicamente las reglas
propias de cada juego.

Principios de POO que se aplican (ver docs/decisiones-tecnicas.md):

* Abstracción: la consola solo conoce ``Game``; no sabe nada de tableros,
  fichas ni minas.
* Encapsulación: el estado interno de cada juego es privado (``_board``...)
  y solo se modifica mediante ``apply``; hacia afuera solo sale ``view()``,
  que además oculta información (las minas) mientras la partida sigue.
* Polimorfismo: ``GameSession`` trata igual a los tres juegos.
* Plantilla de método: ``closing_events`` es común y las subclases solo
  aportan detalles con ``extra_finish_data``.

Los juegos NO saben nada de HTTP, de GameStats ni de Prolog: devuelven
``GameEvent`` de dominio y otra capa (``GameSession``) los convierte al
formato de GameStats y los envía.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Optional


class Outcome(str, Enum):
    """Resultado de una partida, visto desde la persona que juega."""

    WON = "WON"
    LOST = "LOST"
    DRAW = "DRAW"
    ABANDONED = "ABANDONED"


class InvalidAction(Exception):
    """La acción pedida no es válida en el estado actual del juego."""


@dataclass
class GameEvent:
    """Hecho de dominio ocurrido en una partida.

    Todavía no es un evento de GameStats: le faltan eventId, timestamp,
    gameId, matchId, etc. Eso lo agrega ``GameSession`` (ver events.py).
    """

    type: str
    player_id: Optional[str] = None
    action: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)


class Game(ABC):
    """Contrato común de los juegos."""

    #: Identificador estable del juego (campo ``gameId`` en GameStats).
    game_id: ClassVar[str]
    #: Versión de las reglas (campo ``gameVersion`` en GameStats).
    version: ClassVar[str] = "1.0"
    title: ClassVar[str]
    description: ClassVar[str]
    #: Modo de juego informado en MATCH_STARTED.
    mode: ClassVar[str] = "solo"

    def __init__(
        self,
        player_id: str = "player",
        options: Optional[dict[str, Any]] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.player_id = player_id
        self._options = dict(options or {})
        self._rng = rng or random.Random()
        self._outcome: Optional[Outcome] = None
        self._moves = 0

    # ------------------------------------------------------------------ estado

    @property
    def outcome(self) -> Optional[Outcome]:
        return self._outcome

    @property
    def is_over(self) -> bool:
        return self._outcome is not None

    @property
    def moves(self) -> int:
        return self._moves

    @property
    def score(self) -> Optional[int]:
        """Puntaje de la partida, si el juego tiene uno."""
        return None

    @property
    def awaiting_ai(self) -> bool:
        """True si el juego espera la decisión de la computadora (Prolog)."""
        return False

    @property
    def winner_id(self) -> Optional[str]:
        return self.player_id if self._outcome is Outcome.WON else None

    # -------------------------------------------------------------- contrato

    @abstractmethod
    def start_data(self) -> dict[str, Any]:
        """Datos específicos del juego para el evento MATCH_STARTED."""

    @abstractmethod
    def apply(self, action: dict[str, Any]) -> list[GameEvent]:
        """Aplica una acción de la persona y devuelve los eventos generados.

        Lanza :class:`InvalidAction` si la acción no es válida; en ese caso el
        estado del juego no cambia.
        """

    @abstractmethod
    def view(self) -> dict[str, Any]:
        """Estado listo para mostrarse (sin revelar información oculta)."""

    # ---------------------------------------------------------------- común

    def start_events(self) -> list[GameEvent]:
        data = {"mode": self.mode}
        data.update(self.start_data())
        return [GameEvent("MATCH_STARTED", self.player_id, "START", data)]

    def abandon(self) -> None:
        """Marca la partida como abandonada (si todavía estaba en curso)."""
        if not self.is_over:
            self._outcome = Outcome.ABANDONED

    def extra_finish_data(self) -> dict[str, Any]:
        """Datos adicionales para MATCH_FINISHED (las subclases pueden ampliar)."""
        return {}

    def closing_events(self, duration_ms: int) -> list[GameEvent]:
        """Eventos de cierre: resultado (PLAYER_WON/LOST) y MATCH_FINISHED."""
        assert self._outcome is not None, "closing_events solo se llama con la partida terminada"
        events: list[GameEvent] = []
        if self._outcome is Outcome.WON:
            events.append(GameEvent("PLAYER_WON", self.player_id, "RESULT", {"moves": self._moves}))
        elif self._outcome is Outcome.LOST:
            events.append(GameEvent("PLAYER_LOST", self.player_id, "RESULT", {"moves": self._moves}))

        data: dict[str, Any] = {
            "outcome": self._outcome.value,
            "winner": self.winner_id,
            "moves": self._moves,
            "durationMs": duration_ms,
        }
        if self.score is not None:
            data["score"] = self.score
        data.update(self.extra_finish_data())
        events.append(GameEvent("MATCH_FINISHED", self.player_id, "FINISH", data))
        return events

    def _require_playing(self) -> None:
        if self.is_over:
            raise InvalidAction("la partida ya terminó")
