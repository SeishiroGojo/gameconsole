import concurrent.futures

import pytest


def types(ingest, match_id):
    return [e["type"] for e in ingest.by_match(match_id)]


def flush(client):
    client.portal.call(client.publisher.flush)


def test_catalogo_tiene_tres_juegos(client):
    r = client.get("/api/games")
    assert r.status_code == 200
    assert {g["gameId"] for g in r.json()} == {"connect4", "game-2048", "minesweeper"}


def test_partida_de_conecta4_genera_el_ciclo_completo_de_eventos(client, ingest, prolog):
    m = client.post("/api/matches", json={"gameId": "connect4", "options": {"difficulty": "easy"}}).json()
    mid = m["matchId"]
    assert mid.startswith("connect4-")

    r = client.post(f"/api/matches/{mid}/actions", json={"type": "drop", "column": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["state"]["turn"] == "human"  # la IA ya jugó
    assert len(prolog.calls) == 1 and prolog.calls[0]["depth"] == 2  # el estado se envió a Prolog

    client.post(f"/api/matches/{mid}/abandon")
    flush(client)
    assert types(ingest, mid) == ["MATCH_STARTED", "PLAYER_ACTION", "AI_DECISION", "MATCH_FINISHED"]
    ai = [e for e in ingest.by_match(mid) if e["type"] == "AI_DECISION"][0]
    assert ai["data"]["column"] == 0 and ai["data"]["engine"].startswith("swi-prolog")
    finish = ingest.by_match(mid)[-1]
    assert finish["data"]["outcome"] == "ABANDONED"
    # todos los eventos traen los campos exigidos por GameStats
    for e in ingest.by_match(mid):
        assert all(e.get(k) for k in ("eventId", "timestamp", "gameId", "gameVersion", "matchId", "type"))


def test_jugada_invalida_devuelve_400_y_no_genera_evento(client, ingest):
    mid = client.post("/api/matches", json={"gameId": "connect4"}).json()["matchId"]
    r = client.post(f"/api/matches/{mid}/actions", json={"type": "drop", "column": 42})
    assert r.status_code == 400
    flush(client)
    assert types(ingest, mid) == ["MATCH_STARTED"]


def test_juego_desconocido_y_partida_inexistente(client):
    assert client.post("/api/matches", json={"gameId": "tetris"}).status_code == 404
    assert client.get("/api/matches/nope").status_code == 404


def test_si_prolog_falla_la_jugada_queda_pendiente_y_se_puede_reintentar(client, ingest, prolog):
    mid = client.post("/api/matches", json={"gameId": "connect4"}).json()["matchId"]
    prolog.fail = True
    r = client.post(f"/api/matches/{mid}/actions", json={"type": "drop", "column": 0})
    assert r.status_code == 503
    assert r.json()["match"]["state"]["awaitingAi"] is True  # la jugada de la persona sí quedó aplicada

    prolog.fail = False
    r = client.post(f"/api/matches/{mid}/ai")
    assert r.status_code == 200 and r.json()["state"]["awaitingAi"] is False
    flush(client)
    assert types(ingest, mid) == ["MATCH_STARTED", "PLAYER_ACTION", "AI_DECISION"]


def test_2048_y_buscaminas_se_juegan_y_terminan(client, ingest):
    g = client.post("/api/matches", json={"gameId": "game-2048"}).json()
    r = client.get(f"/api/matches/{g['matchId']}").json()
    assert len(r["state"]["board"]) == 4

    b = client.post("/api/matches", json={"gameId": "minesweeper", "options": {"difficulty": "easy"}}).json()
    r = client.post(f"/api/matches/{b['matchId']}/actions", json={"type": "reveal", "row": 4, "col": 4})
    assert r.status_code == 200 and r.json()["state"]["revealed"] >= 1
    client.post(f"/api/matches/{b['matchId']}/abandon")
    flush(client)
    assert types(ingest, b["matchId"])[0] == "MATCH_STARTED" and types(ingest, b["matchId"])[-1] == "MATCH_FINISHED"


def test_muchas_partidas_en_paralelo_no_mezclan_sus_eventos(client, ingest):
    ids = []
    for gid in ("connect4", "game-2048", "minesweeper") * 4:  # 12 instancias a la vez
        ids.append(client.post("/api/matches", json={"gameId": gid}).json()["matchId"])
    assert len(set(ids)) == 12  # matchId único por instancia

    def jugar(mid: str):
        if mid.startswith("connect4"):
            client.post(f"/api/matches/{mid}/actions", json={"type": "drop", "column": 3})
        elif mid.startswith("minesweeper"):
            client.post(f"/api/matches/{mid}/actions", json={"type": "reveal", "row": 4, "col": 4})
        client.post(f"/api/matches/{mid}/abandon")

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(jugar, ids))
    flush(client)

    for mid in ids:
        mine = ingest.by_match(mid)
        assert mine[0]["type"] == "MATCH_STARTED" and mine[-1]["type"] == "MATCH_FINISHED"
        assert {e["gameId"] for e in mine} == {mid.rsplit("-", 5)[0]}  # un solo juego por partida
        assert sum(e["type"] == "MATCH_FINISHED" for e in mine) == 1
    assert len(ingest.events) == sum(len(ingest.by_match(m)) for m in ids)  # nada se perdió ni se duplicó


def test_estadisticas_del_panel_vienen_de_gamestats(client):
    data = client.get("/api/stats/all").json()
    assert data["live"]["totals"]["started"] == 1  # valor devuelto por el GameStats falso, tal cual
    assert data["sources"]["ingestion"]["ok"] and data["sources"]["analysis"]["ok"]
    assert "instances" in data["console"]


def test_panel_avisa_si_gamestats_no_responde(fast_settings, prolog):
    import httpx
    from fastapi.testclient import TestClient

    from app.events import EventPublisher
    from app.main import create_app

    def caido(request):
        raise httpx.ConnectError("caído")

    http = httpx.AsyncClient(transport=httpx.MockTransport(caido))
    app = create_app(fast_settings, publisher=EventPublisher(fast_settings, client=http), prolog=prolog,
                     stats_client=http, start_reaper=False)
    with TestClient(app) as c:
        data = c.get("/api/stats/all").json()
        assert data["sources"]["ingestion"]["ok"] is False and data["live"] is None


@pytest.mark.anyio
async def test_reaper_abandona_partidas_inactivas(client, ingest):
    import asyncio

    mid = client.post("/api/matches", json={"gameId": "game-2048"}).json()["matchId"]
    await asyncio.sleep(0.3)  # idle_timeout de prueba: 0.2 s
    result = client.portal.call(client.registry.reap_once)
    assert result["abandoned"] == 1
    flush(client)
    assert ingest.by_match(mid)[-1]["data"]["outcome"] == "ABANDONED"


def test_partidas_automaticas_se_juegan_en_paralelo_y_terminan(client, ingest):
    import time

    r = client.post("/api/demo/bots", json={"perGame": 2})
    assert r.status_code == 202 and r.json()["launched"] == 6
    ids = set(r.json()["matchIds"])
    assert len(ids) == 6

    limite = time.time() + 20
    while time.time() < limite and not all(client.registry.get(i).is_over for i in ids):
        time.sleep(0.05)
    assert all(client.registry.get(i).is_over for i in ids)

    flush(client)
    for mid in ids:
        mine = ingest.by_match(mid)
        assert mine[0]["type"] == "MATCH_STARTED" and mine[-1]["type"] == "MATCH_FINISHED"
        assert mine[0]["playerId"].startswith("bot-")


def test_limite_de_partidas_automaticas(client):
    assert client.post("/api/demo/bots", json={"perGame": 11}).status_code == 422  # máximo 10 por juego
