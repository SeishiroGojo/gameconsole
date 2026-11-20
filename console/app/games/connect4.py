"""Conecta 4: persona (fichas 1) contra la computadora (fichas 2).

Las decisiones de la computadora NO se calculan aquí: este módulo solo arma
el estado del tablero (``ai_request``), lo entrega a quien llame y aplica la
columna que el servicio Prolog devuelve (``apply_ai``). Ver prolog/.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional

from .base import Game, GameEvent, InvalidAction, Outcome

ROWS, COLS = 6, 7
EMPTY, HUMAN, AI = 0, 1, 2
AI_PLAYER_ID = "prolog-ai"

# Profundidad de búsqueda de la IA según la dificultad.
DEPTH_BY_DIFFICULTY = {"easy": 2, "medium": 4, "hard": 5}


class Connect4Game(Game):
    game_id: ClassVar[str] = "connect4"
    title: ClassVar[str] = "Conecta 4"
    description: ClassVar[str] = "Alinea cuatro fichas antes que la computadora. Su IA está hecha en Prolog."
    mode: ClassVar[str] = "vs_ai"

    def __init__(self, player_id: str = "player", options: Optional[dict[str, Any]] = None, rng=None) -> None:
        super().__init__(player_id, options, rng)
        difficulty = str(self._options.get("difficulty", "medium")).lower()
        if difficulty not in DEPTH_BY_DIFFICULTY:
            raise InvalidAction(f"dificultad desconocida: {difficulty}")
        self._difficulty = difficulty
        self._depth = DEPTH_BY_DIFFICULTY[difficulty]
        # Fila 0 = arriba. Valores: 0 vacío, 1 persona, 2 computadora.
        self._board: list[list[int]] = [[EMPTY] * COLS for _ in range(ROWS)]
        self._awaiting_ai = False
        self._last_move: Optional[dict[str, Any]] = None
        self._winning_cells: list[list[int]] = []
        self._ai_info: Optional[dict[str, Any]] = None

    # ------------------------------------------------------------- propiedades

    @property
    def awaiting_ai(self) -> bool:
        return self._awaiting_ai and not self.is_over

    @property
    def winner_id(self) -> Optional[str]:
        if self._outcome is Outcome.WON:
            return self.player_id
        if self._outcome is Outcome.LOST:
            return AI_PLAYER_ID
        return None

    def start_data(self) -> dict[str, Any]:
        return {
            "difficulty": self._difficulty,
            "searchDepth": self._depth,
            "players": [self.player_id, AI_PLAYER_ID],
            "rows": ROWS,
            "cols": COLS,
        }

    # --------------------------------------------------------------- reglas

    def apply(self, action: dict[str, Any]) -> list[GameEvent]:
        self._require_playing()
        if self._awaiting_ai:
            raise InvalidAction("es el turno de la computadora")
        if action.get("type") != "drop":
            raise InvalidAction("acción desconocida; use {'type': 'drop', 'column': n}")
        col = action.get("column")
        if not isinstance(col, int) or isinstance(col, bool) or not 0 <= col < COLS:
            raise InvalidAction(f"columna inválida (debe estar entre 0 y {COLS - 1})")

        row = self._drop(col, HUMAN)
        self._moves += 1
        self._last_move = {"row": row, "col": col, "by": "human"}
        events = [
            GameEvent(
                "PLAYER_ACTION",
                self.player_id,
                "DROP_DISC",
                {"column": col, "row": row, "board": self.snapshot()},
            )
        ]
        self._settle(HUMAN)
        if not self.is_over:
            self._awaiting_ai = True
        return events

    def ai_request(self) -> dict[str, Any]:
        """Estado que se envía a Prolog para que decida la jugada."""
        return {"board": self.snapshot(), "player": AI, "depth": self._depth}

    def apply_ai(self, decision: dict[str, Any], latency_ms: int) -> list[GameEvent]:
        """Aplica la jugada que Prolog eligió y devuelve el evento AI_DECISION."""
        self._require_playing()
        if not self._awaiting_ai:
            raise InvalidAction("la computadora no tiene un turno pendiente")
        col = decision.get("column")
        if not isinstance(col, int) or not 0 <= col < COLS or self._board[0][col] != EMPTY:
            raise InvalidAction(f"Prolog devolvió una columna inválida: {col!r}")

        state_before = self.snapshot()
        row = self._drop(col, AI)
        self._awaiting_ai = False
        self._last_move = {"row": row, "col": col, "by": "ai"}
        self._ai_info = {
            "column": col,
            "score": decision.get("score"),
            "nodes": decision.get("nodes"),
            "depth": decision.get("depth", self._depth),
            "latencyMs": latency_ms,
            "candidates": decision.get("candidates", []),
        }
        event = GameEvent(
            "AI_DECISION",
            AI_PLAYER_ID,
            "CHOOSE_COLUMN",
            {
                "state": state_before,
                "column": col,
                "row": row,
                "score": decision.get("score"),
                "nodes": decision.get("nodes"),
                "depth": decision.get("depth", self._depth),
                "latencyMs": latency_ms,
                "engine": "swi-prolog negamax alfa-beta",
            },
        )
        self._settle(AI)
        return [event]

    def snapshot(self) -> list[list[int]]:
        return [row[:] for row in self._board]

    # -------------------------------------------------------------- internos

    def _drop(self, col: int, who: int) -> int:
        for row in range(ROWS - 1, -1, -1):
            if self._board[row][col] == EMPTY:
                self._board[row][col] = who
                return row
        raise InvalidAction("esa columna está llena")

    def _settle(self, who: int) -> None:
        """Comprueba si la última jugada ganó o empató la partida."""
        cells = self._find_four(who)
        if cells:
            self._winning_cells = [list(c) for c in cells]
            self._outcome = Outcome.WON if who == HUMAN else Outcome.LOST
        elif all(self._board[0][c] != EMPTY for c in range(COLS)):
            self._outcome = Outcome.DRAW

    def _find_four(self, who: int) -> Optional[list[tuple[int, int]]]:
        for r in range(ROWS):
            for c in range(COLS):
                for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                    cells = [(r + k * dr, c + k * dc) for k in range(4)]
                    if all(0 <= rr < ROWS and 0 <= cc < COLS and self._board[rr][cc] == who for rr, cc in cells):
                        return cells
        return None

    def extra_finish_data(self) -> dict[str, Any]:
        return {"difficulty": self._difficulty}

    def view(self) -> dict[str, Any]:
        return {
            "board": self.snapshot(),
            "rows": ROWS,
            "cols": COLS,
            "turn": "ai" if self.awaiting_ai else "human",
            "awaitingAi": self.awaiting_ai,
            "difficulty": self._difficulty,
            "lastMove": self._last_move,
            "winningCells": self._winning_cells,
            "aiInfo": self._ai_info,
        }
