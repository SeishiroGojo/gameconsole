% Inteligencia artificial de Conecta 4 en Prolog.
%
% La computadora NO juega al azar: busca la mejor jugada con el algoritmo
% negamax con poda alfa-beta (una variante de minimax) hasta una profundidad
% dada, y evalua las posiciones con una heuristica de "ventanas" de cuatro
% casillas. Todo el razonamiento esta en reglas Prolog.
%
% Representacion del tablero: lista de 7 columnas (la 0 es la de la izquierda).
% Cada columna es una lista de fichas de ABAJO hacia ARRIBA (1 = persona,
% 2 = computadora). Ejemplo: [[1,2],[],[2],[],[],[],[]] tiene dos fichas en la
% columna 0 (la de abajo es del jugador 1) y una en la columna 2.

:- module(connect4_ai, [
    board_from_rows/2,
    best_move/6,
    legal_moves/2,
    drop/4,
    wins/2
]).

:- use_module(library(lists)).
:- use_module(library(apply)).

cols(7).
rows(6).

% Orden de exploracion: de las columnas centrales a las laterales.
% Probar primero las mejores jugadas hace mucho mas eficaz la poda alfa-beta.
move_order([3,2,4,1,5,0,6]).

% ---------------------------------------------------------------------------
% Conversion desde el formato del juego (filas de arriba hacia abajo)
% ---------------------------------------------------------------------------

% board_from_rows(+Filas, -Tablero): Filas es una lista de 6 listas de 7
% numeros (0 = vacio), la primera fila es la de arriba.
board_from_rows(Rows, Board) :-
    reverse(Rows, BottomUp),
    numlist(0, 6, ColIdx),
    maplist(column_from_rows(BottomUp), ColIdx, Board).

column_from_rows(BottomUpRows, C, Column) :-
    findall(P, (member(Row, BottomUpRows), nth0(C, Row, P)), Cells),
    take_pieces(Cells, Column).

take_pieces([], []).
take_pieces([0|_], []) :- !.
take_pieces([P|T], [P|R]) :- take_pieces(T, R).

% ---------------------------------------------------------------------------
% Reglas del juego
% ---------------------------------------------------------------------------

legal_moves(Board, Moves) :-
    move_order(Order),
    rows(Rows),
    include(can_drop(Board, Rows), Order, Moves).

can_drop(Board, Rows, C) :-
    nth0(C, Board, Column),
    length(Column, N),
    N < Rows.

% drop(+Tablero, +Columna, +Jugador, -NuevoTablero)
drop(Board, C, Player, NewBoard) :-
    nth0(C, Board, Column, Rest),
    append(Column, [Player], NewColumn),
    nth0(C, NewBoard, NewColumn, Rest).

% cell(+Tablero, +Col, +Fila, -Ficha): 0 si esta vacia; falla fuera del tablero.
cell(Board, C, R, P) :-
    cols(NC), rows(NR),
    C >= 0, C < NC, R >= 0, R < NR,
    nth0(C, Board, Column),
    (   nth0(R, Column, P0) -> P = P0 ; P = 0 ).

% Las 69 "ventanas" de cuatro casillas consecutivas (horizontal, vertical y
% las dos diagonales). Se calculan una sola vez.
:- dynamic window_cache/1.

windows(Ws) :-
    window_cache(Ws), !.
windows(Ws) :-
    findall(W,
            ( member(D, [(1,0),(0,1),(1,1),(1,-1)]),
              D = (DC,DR),
              between(0, 6, C0), between(0, 5, R0),
              C3 is C0 + 3*DC, R3 is R0 + 3*DR,
              C3 >= 0, C3 =< 6, R3 >= 0, R3 =< 5,
              findall(C-R, ( between(0, 3, K),
                             C is C0 + K*DC, R is R0 + K*DR ), W)
            ),
            Ws),
    assertz(window_cache(Ws)).

window_values(Board, Window, Values) :-
    findall(P, ( member(C-R, Window), cell(Board, C, R, P) ), Values).

% wins(+Tablero, +Jugador): el jugador tiene cuatro en linea.
wins(Board, Player) :-
    windows(Ws),
    member(W, Ws),
    window_values(Board, W, Vs),
    maplist(==(Player), Vs), !.

other(1, 2).
other(2, 1).

% ---------------------------------------------------------------------------
% Heuristica: puntua el tablero desde el punto de vista de Player
% ---------------------------------------------------------------------------

evaluate(Board, Player, Score) :-
    other(Player, Opp),
    windows(Ws),
    foldl(score_window(Board, Player, Opp), Ws, 0, WindowScore),
    center_score(Board, Player, Opp, CenterScore),
    Score is WindowScore + CenterScore.

score_window(Board, Player, Opp, Window, Acc0, Acc) :-
    window_values(Board, Window, Vs),
    include(==(Player), Vs, Mine), length(Mine, M),
    include(==(Opp), Vs, Theirs), length(Theirs, T),
    include(==(0), Vs, Empty), length(Empty, E),
    window_points(M, T, E, Pts),
    Acc is Acc0 + Pts.

% Tres propias y un hueco: casi una victoria. Tres del rival y un hueco: hay
% que bloquear. Dos y dos huecos: potencial.
window_points(3, 0, 1,   50) :- !.
window_points(2, 0, 2,   10) :- !.
window_points(0, 3, 1,  -60) :- !.
window_points(0, 2, 2,  -10) :- !.
window_points(_, _, _,    0).

% La columna central participa en mas lineas, asi que vale mas.
center_score(Board, Player, Opp, Score) :-
    nth0(3, Board, Center),
    include(==(Player), Center, Mine), length(Mine, M),
    include(==(Opp), Center, Theirs), length(Theirs, T),
    Score is 6 * (M - T).

% ---------------------------------------------------------------------------
% Busqueda: negamax con poda alfa-beta
% ---------------------------------------------------------------------------

win_score(Depth, Score) :- Score is 100000 + Depth.

% negamax(+Tablero, +Jugador, +Profundidad, +Alfa, +Beta, -Puntaje)
% Puntaje es el valor de la posicion para Jugador (el que mueve ahora).
negamax(Board, Player, Depth, Alpha, Beta, Score) :-
    bump_nodes,
    other(Player, Opp),
    (   wins(Board, Opp)
    ->  win_score(Depth, W), Score is -W          % el rival ya gano
    ;   legal_moves(Board, Moves),
        (   Moves == []
        ->  Score = 0                             % empate: tablero lleno
        ;   Depth =:= 0
        ->  evaluate(Board, Player, Score)
        ;   D1 is Depth - 1,
            search_moves(Moves, Board, Player, D1, Alpha, Beta, -1000000, Score)
        )
    ).

search_moves([], _, _, _, _, _, Best, Best).
search_moves([M|Ms], Board, Player, D1, Alpha, Beta, Best0, Best) :-
    drop(Board, M, Player, Child),
    other(Player, Opp),
    NA is -Beta, NB is -Alpha,
    negamax(Child, Opp, D1, NA, NB, V0),
    V is -V0,
    Best1 is max(Best0, V),
    Alpha1 is max(Alpha, Best1),
    (   Alpha1 >= Beta
    ->  Best = Best1                              % poda: el resto no importa
    ;   search_moves(Ms, Board, Player, D1, Alpha1, Beta, Best1, Best)
    ).

bump_nodes :-
    nb_getval(c4_nodes, N0), N is N0 + 1, nb_setval(c4_nodes, N).

% best_move(+Tablero, +Jugador, +Profundidad, -Columna, -Puntaje, -Detalle)
% Detalle es la lista Columna-Puntaje de todas las jugadas evaluadas y el
% numero de nodos explorados: Detalle = info(Candidatos, Nodos).
best_move(Board, Player, Depth, BestCol, BestScore, info(Candidates, Nodes)) :-
    nb_setval(c4_nodes, 0),
    legal_moves(Board, Moves),
    Moves \== [],
    D1 is Depth - 1,
    other(Player, Opp),
    findall(Col-Score,
            ( member(Col, Moves),
              drop(Board, Col, Player, Child),
              (   wins(Child, Player)
              ->  win_score(Depth, S0), Score = S0
              ;   negamax(Child, Opp, D1, -1000000, 1000000, V0),
                  Score is -V0
              )
            ),
            Candidates),
    pick_best(Candidates, BestCol, BestScore),
    nb_getval(c4_nodes, Nodes).

% El mejor puntaje; si hay empate gana la primera (la mas central).
pick_best([C-S|Rest], BestC, BestS) :-
    foldl([C1-S1, C0-S0, Cn-Sn]>>( S1 > S0 -> Cn-Sn = C1-S1 ; Cn-Sn = C0-S0 ),
          Rest, C-S, BestC-BestS).
