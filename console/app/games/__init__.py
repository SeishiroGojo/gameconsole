"""Catálogo de juegos de la consola: exactamente tres."""

from .base import Game, GameEvent, InvalidAction, Outcome
from .connect4 import Connect4Game
from .game2048 import Game2048
from .minesweeper import MinesweeperGame

GAME_CLASSES: dict[str, type[Game]] = {
    cls.game_id: cls for cls in (Connect4Game, Game2048, MinesweeperGame)
}

__all__ = [
    "Game", "GameEvent", "InvalidAction", "Outcome",
    "Connect4Game", "Game2048", "MinesweeperGame", "GAME_CLASSES",
]
