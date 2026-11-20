"""Buscaminas: descubre todas las casillas seguras sin pisar una mina."""

from __future__ import annotations

from collections import deque
from typing import Any, ClassVar, Optional

from .base import Game, GameEvent, InvalidAction, Outcome

PRESETS = {
    "easy": (9, 9, 10),
    "medium": (12, 12, 24),
    "hard": (16, 16, 40),
}


class MinesweeperGame(Game):
    game_id: ClassVar[str] = "minesweeper"
    title: ClassVar[str] = "Buscaminas"
    description: ClassVar[str] = "Descubre las casillas seguras con ayuda de los números. La primera jugada nunca es mina."
    mode: ClassVar[str] = "solo"

    def __init__(self, player_id: str = "player", options: Optional[dict[str, Any]] = None, rng=None) -> None:
        super().__init__(player_id, options, rng)
        difficulty = str(self._options.get("difficulty", "easy")).lower()
        if difficulty not in PRESETS:
            raise InvalidAction(f"dificultad desconocida: {difficulty}")
        self._difficulty = difficulty
        self._rows, self._cols, self._mine_count = PRESETS[difficulty]
        self._mines: set[tuple[int, int]] = set()  # se colocan en la primera jugada
        self._revealed: set[tuple[int, int]] = set()
        self._flags: set[tuple[int, int]] = set()
        self._exploded: Optional[tuple[int, int]] = None

    @property
    def score(self) -> Optional[int]:
        return len(self._revealed)

    def start_data(self) -> dict[str, Any]:
        return {"difficulty": self._difficulty, "rows": self._rows, "cols": self._cols, "mines": self._mine_count}

    # --------------------------------------------------------------- acciones

    def apply(self, action: dict[str, Any]) -> list[GameEvent]:
        self._require_playing()
        kind = action.get("type")
        if kind not in ("reveal", "flag"):
            raise InvalidAction("acción desconocida; use 'reveal' o 'flag' con row y col")
        row, col = action.get("row"), action.get("col")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (row, col)):
            raise InvalidAction("row y col deben ser enteros")
        if not (0 <= row < self._rows and 0 <= col < self._cols):
            raise InvalidAction("casilla fuera del tablero")
        cell = (row, col)

        if kind == "flag":
            return [self._toggle_flag(cell)]
        return [self._reveal(cell)]

    def _toggle_flag(self, cell: tuple[int, int]) -> GameEvent:
        if cell in self._revealed:
            raise InvalidAction("no se puede marcar una casilla ya descubierta")
        if cell in self._flags:
            self._flags.remove(cell)
            result = "unflag"
        else:
            self._flags.add(cell)
            result = "flag"
        self._moves += 1
        return GameEvent("PLAYER_ACTION", self.player_id, "FLAG", {"row": cell[0], "col": cell[1], "result": result})

    def _reveal(self, cell: tuple[int, int]) -> GameEvent:
        if cell in self._flags:
            raise InvalidAction("quita la bandera antes de descubrir la casilla")
        if cell in self._revealed:
            raise InvalidAction("la casilla ya está descubierta")

        if not self._mines:
            self._place_mines(safe=cell)
        self._moves += 1

        if cell in self._mines:
            self._exploded = cell
            self._outcome = Outcome.LOST
            return GameEvent(
                "PLAYER_ACTION", self.player_id, "REVEAL", {"row": cell[0], "col": cell[1], "result": "mine"}
            )

        before = len(self._revealed)
        self._flood_reveal(cell)
        opened = len(self._revealed) - before
        if len(self._revealed) == self._rows * self._cols - self._mine_count:
            self._outcome = Outcome.WON
        return GameEvent(
            "PLAYER_ACTION",
            self.player_id,
            "REVEAL",
            {"row": cell[0], "col": cell[1], "result": "safe", "opened": opened, "revealed": len(self._revealed)},
        )

    # ---------------------------------------------------------------- reglas

    def _neighbors(self, cell: tuple[int, int]):
        r, c = cell
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if (dr or dc) and 0 <= r + dr < self._rows and 0 <= c + dc < self._cols:
                    yield (r + dr, c + dc)

    def _place_mines(self, safe: tuple[int, int]) -> None:
        """Coloca las minas evitando la casilla inicial y sus vecinas."""
        forbidden = {safe, *self._neighbors(safe)}
        candidates = [
            (r, c) for r in range(self._rows) for c in range(self._cols) if (r, c) not in forbidden
        ]
        self._mines = set(self._rng.sample(candidates, self._mine_count))

    def _adjacent_mines(self, cell: tuple[int, int]) -> int:
        return sum(1 for n in self._neighbors(cell) if n in self._mines)

    def _flood_reveal(self, start: tuple[int, int]) -> None:
        """Descubre la casilla y, si no tiene minas alrededor, expande."""
        queue = deque([start])
        while queue:
            cell = queue.popleft()
            if cell in self._revealed or cell in self._flags:
                continue
            self._revealed.add(cell)
            if self._adjacent_mines(cell) == 0:
                queue.extend(n for n in self._neighbors(cell) if n not in self._revealed)

    # ----------------------------------------------------------------- vista

    def extra_finish_data(self) -> dict[str, Any]:
        return {"difficulty": self._difficulty, "revealed": len(self._revealed)}

    def view(self) -> dict[str, Any]:
        over = self.is_over
        cells: list[list[dict[str, Any]]] = []
        for r in range(self._rows):
            row = []
            for c in range(self._cols):
                cell = (r, c)
                if cell in self._revealed:
                    row.append({"s": "open", "n": self._adjacent_mines(cell)})
                elif cell in self._flags:
                    row.append({"s": "flag", "wrong": over and cell not in self._mines})
                elif over and cell in self._mines:
                    row.append({"s": "mine", "boom": cell == self._exploded})
                else:
                    row.append({"s": "hidden"})  # las minas NO se revelan mientras se juega
            cells.append(row)
        return {
            "cells": cells,
            "rows": self._rows,
            "cols": self._cols,
            "mines": self._mine_count,
            "flagsLeft": self._mine_count - len(self._flags),
            "revealed": len(self._revealed),
            "difficulty": self._difficulty,
        }
