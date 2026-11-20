"""2048: desliza las fichas y combina las iguales hasta llegar a 2048."""

from __future__ import annotations

from typing import Any, ClassVar, Optional

from .base import Game, GameEvent, InvalidAction, Outcome

SIZE = 4
TARGET = 2048
DIRECTIONS = ("up", "down", "left", "right")


def _slide_line_left(line: list[int]) -> tuple[list[int], int]:
    """Desliza una fila hacia la izquierda y devuelve (fila, puntos ganados).

    Función pura: es el corazón de las reglas y se prueba por separado.
    """
    tiles = [v for v in line if v]
    merged: list[int] = []
    gained = 0
    i = 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
            value = tiles[i] * 2
            merged.append(value)
            gained += value
            i += 2
        else:
            merged.append(tiles[i])
            i += 1
    merged += [0] * (len(line) - len(merged))
    return merged, gained


class Game2048(Game):
    game_id: ClassVar[str] = "game-2048"
    title: ClassVar[str] = "2048"
    description: ClassVar[str] = "Combina fichas iguales con las flechas del teclado hasta formar 2048."
    mode: ClassVar[str] = "solo"

    def __init__(self, player_id: str = "player", options: Optional[dict[str, Any]] = None, rng=None) -> None:
        super().__init__(player_id, options, rng)
        self._board: list[list[int]] = [[0] * SIZE for _ in range(SIZE)]
        self._score = 0
        self._spawn()
        self._spawn()

    @property
    def score(self) -> Optional[int]:
        return self._score

    @property
    def max_tile(self) -> int:
        return max(max(row) for row in self._board)

    def start_data(self) -> dict[str, Any]:
        return {"size": SIZE, "target": TARGET}

    def apply(self, action: dict[str, Any]) -> list[GameEvent]:
        self._require_playing()
        if action.get("type") != "move":
            raise InvalidAction("acción desconocida; use {'type': 'move', 'direction': 'up|down|left|right'}")
        direction = action.get("direction")
        if direction not in DIRECTIONS:
            raise InvalidAction(f"dirección inválida: {direction!r}")

        new_board, gained = self._slide(self._board, direction)
        if new_board == self._board:
            raise InvalidAction("ese movimiento no cambia el tablero")

        self._board = new_board
        self._score += gained
        self._moves += 1
        spawned = self._spawn()

        if self.max_tile >= TARGET:
            self._outcome = Outcome.WON
        elif not self._can_move():
            self._outcome = Outcome.LOST

        return [
            GameEvent(
                "PLAYER_ACTION",
                self.player_id,
                "SLIDE",
                {
                    "direction": direction,
                    "gained": gained,
                    "score": self._score,
                    "maxTile": self.max_tile,
                    "spawned": spawned,
                },
            )
        ]

    # --------------------------------------------------------------- reglas

    @staticmethod
    def _slide(board: list[list[int]], direction: str) -> tuple[list[list[int]], int]:
        gained = 0
        if direction in ("left", "right"):
            rows = []
            for row in board:
                line = row[::-1] if direction == "right" else row[:]
                slid, g = _slide_line_left(line)
                gained += g
                rows.append(slid[::-1] if direction == "right" else slid)
            return rows, gained
        # up / down: se trabaja sobre las columnas
        cols = [[board[r][c] for r in range(SIZE)] for c in range(SIZE)]
        new_cols = []
        for col in cols:
            line = col[::-1] if direction == "down" else col[:]
            slid, g = _slide_line_left(line)
            gained += g
            new_cols.append(slid[::-1] if direction == "down" else slid)
        return [[new_cols[c][r] for c in range(SIZE)] for r in range(SIZE)], gained

    def _can_move(self) -> bool:
        return any(self._slide(self._board, d)[0] != self._board for d in DIRECTIONS)

    def _spawn(self) -> Optional[dict[str, int]]:
        empty = [(r, c) for r in range(SIZE) for c in range(SIZE) if self._board[r][c] == 0]
        if not empty:
            return None
        r, c = self._rng.choice(empty)
        value = 4 if self._rng.random() < 0.1 else 2
        self._board[r][c] = value
        return {"row": r, "col": c, "value": value}

    def extra_finish_data(self) -> dict[str, Any]:
        return {"maxTile": self.max_tile}

    def view(self) -> dict[str, Any]:
        return {
            "board": [row[:] for row in self._board],
            "size": SIZE,
            "score": self._score,
            "maxTile": self.max_tile,
            "target": TARGET,
        }
