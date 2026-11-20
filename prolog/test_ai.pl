% Pruebas de la IA de Conecta 4. Ejecutar con:
%   swipl -g run_tests -t halt test_ai.pl
:- use_module(library(plunit)).
:- use_module(connect4_ai).

% Atajo: arma un tablero desde columnas (abajo -> arriba).
b(Cols, Cols).

:- begin_tests(connect4_ai).

test(tablero_vacio_elige_el_centro) :-
    b([[],[],[],[],[],[],[]], B),
    best_move(B, 2, 4, Col, _, _),
    Col =:= 3.

test(gana_si_puede) :-
    % La computadora (2) tiene tres en la fila de abajo: columnas 0,1,2.
    b([[2],[2],[2],[],[1],[1],[]], B),
    best_move(B, 2, 4, Col, _, _),
    Col =:= 3.

test(bloquea_al_rival) :-
    % La persona (1) amenaza con ganar en la columna 3 (tiene 0,1,2 abajo).
    b([[1],[1],[1],[],[2],[2],[]], B),
    best_move(B, 2, 4, Col, _, _),
    Col =:= 3.

test(prefiere_ganar_a_bloquear) :-
    % Ambos pueden ganar en la columna 3; la computadora debe ganar, no bloquear.
    b([[2],[2],[2],[],[1,1],[1],[1]], B),
    best_move(B, 2, 4, Col, Score, _),
    Col =:= 3,
    Score > 100000.

test(no_juega_en_columna_llena) :-
    b([[1,2,1,2,1,2],[],[],[],[],[],[]], B),
    legal_moves(B, Moves),
    \+ memberchk(0, Moves).

test(detecta_cuatro_en_diagonal) :-
    b([[1],[2,1],[2,2,1],[2,2,2,1],[],[],[]], B),
    wins(B, 1).

test(convierte_filas_a_columnas) :-
    Rows = [[0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0],
            [0,0,0,0,0,0,0],
            [0,0,0,0,0,0,2],
            [1,2,0,0,0,0,1]],
    board_from_rows(Rows, B),
    B == [[1],[2],[],[],[],[],[1,2]].

test(termina_rapido_con_profundidad_5, [true(Elapsed < 5.0)]) :-
    b([[1,2],[2],[1],[],[2,1],[],[1]], B),
    get_time(T0),
    best_move(B, 2, 5, _, _, _),
    get_time(T1),
    Elapsed is T1 - T0.

:- end_tests(connect4_ai).
