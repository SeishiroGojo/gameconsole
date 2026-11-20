import random

import pytest

from app.games import GAME_CLASSES, Connect4Game, Game, Game2048, InvalidAction, MinesweeperGame, Outcome
from app.games.game2048 import _slide_line_left


def test_hay_exactamente_tres_juegos_distintos():
    assert set(GAME_CLASSES) == {"connect4", "game-2048", "minesweeper"}
    assert all(issubclass(c, Game) for c in GAME_CLASSES.values())


def test_game_es_abstracta():
    with pytest.raises(TypeError):
        Game()  # type: ignore[abstract]


# ----------------------------------------------------------------- Conecta 4


def human_wins_horizontally(game: Connect4Game):
    """La persona juega 0,1,2,3 en la fila de abajo; la 'IA' responde en la fila de arriba."""
    for col in (0, 1, 2, 3):
        game.apply({"type": "drop", "column": col})
        if game.awaiting_ai:
            ai_col = 6 if col % 2 == 0 else 5
            game.apply_ai({"column": ai_col, "score": 0, "nodes": 1}, 1)


def test_connect4_victoria_horizontal_de_la_persona():
    g = Connect4Game()
    human_wins_horizontally(g)
    assert g.outcome is Outcome.WON
    assert g.winner_id == "player"
    assert g.view()["winningCells"]


def test_connect4_victoria_vertical_y_diagonal():
    g = Connect4Game()
    for _ in range(3):
        g.apply({"type": "drop", "column": 0})
        g.apply_ai({"column": 1, "score": 0}, 1)
    g.apply({"type": "drop", "column": 0})
    assert g.outcome is Outcome.WON  # cuatro en la columna 0

    d = Connect4Game()
    d._board = [[0] * 7 for _ in range(6)]
    for i in range(4):
        d._board[5 - i][i] = 1
    assert d._find_four(1) is not None  # diagonal ascendente


def test_connect4_turnos_y_columnas_invalidas():
    g = Connect4Game()
    with pytest.raises(InvalidAction):
        g.apply({"type": "drop", "column": 9})
    g.apply({"type": "drop", "column": 3})
    assert g.awaiting_ai
    with pytest.raises(InvalidAction):  # turno de la computadora
        g.apply({"type": "drop", "column": 3})
    with pytest.raises(InvalidAction):  # Prolog devuelve una columna inexistente
        g.apply_ai({"column": 99}, 1)
    g.apply_ai({"column": 3, "score": 1}, 1)
    assert not g.awaiting_ai and g.snapshot()[4][3] == 2  # la ficha cae sobre la de la persona


def test_connect4_columna_llena():
    g = Connect4Game()
    for _ in range(3):
        g.apply({"type": "drop", "column": 0})
        g.apply_ai({"column": 0}, 1)
    with pytest.raises(InvalidAction):
        g.apply({"type": "drop", "column": 0})
    assert g.moves == 3  # la jugada inválida no cuenta


def test_connect4_ia_gana_y_genera_player_lost():
    g = Connect4Game()
    for col in (0, 1, 2):
        g.apply({"type": "drop", "column": 6 - col if col == 0 else col + 3})
        g.apply_ai({"column": col, "score": 0}, 1)
    # La IA tiene 0,1,2 abajo; la persona juega lejos y la IA completa la fila
    g.apply({"type": "drop", "column": 6})
    g.apply_ai({"column": 3, "score": 0}, 1)
    assert g.outcome is Outcome.LOST
    types = [e.type for e in g.closing_events(1000)]
    assert types == ["PLAYER_LOST", "MATCH_FINISHED"]


def test_connect4_dificultad_invalida():
    with pytest.raises(InvalidAction):
        Connect4Game(options={"difficulty": "imposible"})


def test_connect4_ai_request_es_el_estado_que_recibe_prolog():
    g = Connect4Game(options={"difficulty": "hard"})
    g.apply({"type": "drop", "column": 3})
    req = g.ai_request()
    assert req["player"] == 2 and req["depth"] == 5
    assert req["board"][5][3] == 1 and len(req["board"]) == 6 and len(req["board"][0]) == 7


# ---------------------------------------------------------------------- 2048


def test_2048_deslizar_una_fila():
    assert _slide_line_left([2, 2, 2, 2]) == ([4, 4, 0, 0], 8)
    assert _slide_line_left([2, 0, 2, 4]) == ([4, 4, 0, 0], 4)
    assert _slide_line_left([4, 2, 0, 0]) == ([4, 2, 0, 0], 0)
    assert _slide_line_left([2, 2, 4, 4])[0] == [4, 8, 0, 0]


def test_2048_movimiento_actualiza_puntaje_y_genera_ficha():
    g = Game2048(rng=random.Random(1))
    g._board = [[2, 2, 0, 0], [0] * 4, [0] * 4, [0] * 4]
    events = g.apply({"type": "move", "direction": "left"})
    assert events[0].action == "SLIDE" and events[0].data["gained"] == 4
    assert g.score == 4 and g.moves == 1
    assert sum(1 for r in g.view()["board"] for v in r if v) == 2  # el 4 + la ficha nueva


def test_2048_movimiento_sin_efecto_es_invalido():
    g = Game2048(rng=random.Random(1))
    g._board = [[2, 4, 8, 16], [0] * 4, [0] * 4, [0] * 4]
    with pytest.raises(InvalidAction):
        g.apply({"type": "move", "direction": "left"})
    assert g.moves == 0


def test_2048_gana_al_formar_2048_y_pierde_sin_movimientos():
    g = Game2048(rng=random.Random(1))
    g._board = [[1024, 1024, 0, 0], [0] * 4, [0] * 4, [0] * 4]
    g.apply({"type": "move", "direction": "left"})
    assert g.outcome is Outcome.WON

    p = Game2048(rng=random.Random(1))
    # Al deslizar a la derecha solo queda libre la casilla (3,0); ni un 2 ni un 4 pueden combinarse allí.
    p._board = [[2, 4, 2, 4], [4, 2, 4, 2], [8, 32, 8, 32], [16, 64, 0, 128]]
    p.apply({"type": "move", "direction": "right"})
    assert p.outcome is Outcome.LOST


# ----------------------------------------------------------------- Buscaminas


def test_buscaminas_la_primera_jugada_nunca_es_mina():
    for seed in range(30):
        g = MinesweeperGame(rng=random.Random(seed))
        g.apply({"type": "reveal", "row": 4, "col": 4})
        assert not g.is_over
        assert (4, 4) not in g._mines and len(g._mines) == 10


def test_buscaminas_no_revela_minas_mientras_se_juega():
    g = MinesweeperGame(rng=random.Random(3))
    g.apply({"type": "reveal", "row": 0, "col": 0})
    flat = [c for row in g.view()["cells"] for c in row]
    assert not any(c["s"] == "mine" for c in flat)


def test_buscaminas_perder_y_ganar():
    g = MinesweeperGame(rng=random.Random(5))
    g.apply({"type": "reveal", "row": 0, "col": 0})
    mine = next(iter(g._mines))
    g.apply({"type": "reveal", "row": mine[0], "col": mine[1]})
    assert g.outcome is Outcome.LOST
    assert any(c["s"] == "mine" for row in g.view()["cells"] for c in row)  # al perder se muestran

    w = MinesweeperGame(rng=random.Random(5))
    w.apply({"type": "reveal", "row": 0, "col": 0})
    for r in range(w._rows):
        for c in range(w._cols):
            if (r, c) not in w._mines and (r, c) not in w._revealed and not w.is_over:
                w.apply({"type": "reveal", "row": r, "col": c})
    assert w.outcome is Outcome.WON


def test_buscaminas_banderas():
    g = MinesweeperGame(rng=random.Random(2))
    g.apply({"type": "flag", "row": 8, "col": 8})
    assert g.view()["flagsLeft"] == 9
    with pytest.raises(InvalidAction):
        g.apply({"type": "reveal", "row": 8, "col": 8})  # tiene bandera
    g.apply({"type": "flag", "row": 8, "col": 8})
    assert g.view()["flagsLeft"] == 10


def test_buscaminas_acciones_invalidas():
    g = MinesweeperGame()
    for bad in ({"type": "reveal", "row": 99, "col": 0}, {"type": "x"}, {"type": "reveal", "row": "a", "col": 1}):
        with pytest.raises(InvalidAction):
            g.apply(bad)


# ------------------------------------------------------------ eventos de cierre


def test_eventos_de_cierre_incluyen_resultado_puntaje_y_duracion():
    g = Game2048(rng=random.Random(1))
    g._board = [[1024, 1024, 0, 0], [0] * 4, [0] * 4, [0] * 4]
    g.apply({"type": "move", "direction": "left"})
    won, finished = g.closing_events(5000)
    assert won.type == "PLAYER_WON" and finished.type == "MATCH_FINISHED"
    assert finished.data["outcome"] == "WON" and finished.data["score"] == 2048 and finished.data["durationMs"] == 5000


def test_abandonar_solo_genera_match_finished():
    g = Connect4Game()
    g.abandon()
    events = g.closing_events(10)
    assert [e.type for e in events] == ["MATCH_FINISHED"] and events[0].data["outcome"] == "ABANDONED"
