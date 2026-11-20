% Servicio HTTP de la IA de Conecta 4.
%
%   POST /move   {"board": [[0,...],...6 filas...], "player": 2, "depth": 5}
%        ->      {"column": 3, "score": 120, "nodes": 4821, "candidates": [...]}
%   GET  /health -> {"status": "ok"}
%
% "board" son las 6 filas del tablero (la primera es la de arriba), con
% 0 = vacio, 1 = persona, 2 = computadora.

:- use_module(library(http/thread_httpd)).
:- use_module(library(http/http_dispatch)).
:- use_module(library(http/http_json)).
:- use_module(library(http/json)).
:- use_module(connect4_ai).

:- http_handler(root(health), health, []).
:- http_handler(root(move), move, [method(post)]).

health(_Request) :-
    reply_json_dict(_{status: "ok", service: "prolog-connect4"}).

move(Request) :-
    catch(
        ( http_read_json_dict(Request, In),
          handle_move(In) ),
        Err,
        ( term_string(Err, Msg),
          reply_json_dict(_{error: Msg}, [status(400)]) )
    ).

handle_move(In) :-
    Rows = In.board,
    Player = In.get(player, 2),
    Depth0 = In.get(depth, 5),
    Depth is max(1, min(8, Depth0)),
    (   valid_rows(Rows)
    ->  board_from_rows(Rows, Board),
        (   best_move(Board, Player, Depth, Col, Score, info(Cands, Nodes))
        ->  findall(_{column: C, score: S}, member(C-S, Cands), CandJson),
            reply_json_dict(_{column: Col, score: Score, nodes: Nodes,
                              depth: Depth, candidates: CandJson})
        ;   reply_json_dict(_{error: "no hay jugadas posibles"}, [status(422)])
        )
    ;   reply_json_dict(_{error: "el tablero debe tener 6 filas de 7 columnas"},
                        [status(400)])
    ).

valid_rows(Rows) :-
    is_list(Rows), length(Rows, 6),
    forall(member(R, Rows),
           ( is_list(R), length(R, 7), forall(member(X, R), memberchk(X, [0,1,2])) )).

server(Port) :-
    http_server(http_dispatch, [port(Port)]).

main :-
    getenv_port(Port),
    server(Port),
    format(user_error, "Prolog Connect4 escuchando en el puerto ~w~n", [Port]),
    thread_get_message(_).

getenv_port(Port) :-
    (   getenv('PORT', P) -> atom_number(P, Port) ; Port = 8090 ).
