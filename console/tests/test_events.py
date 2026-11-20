import asyncio
import re

import httpx

from app.config import Settings
from app.events import EventPublisher, to_gamestats_event
from app.games.base import GameEvent
from tests.conftest import FakeIngest

RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
SETTINGS = Settings(publish_backoff_seconds=0.01, publish_max_attempts=4)


def ev(match: str, kind: str = "PLAYER_ACTION", n: int = 0) -> dict:
    return to_gamestats_event(
        GameEvent(kind, "player", "X", {"n": n}), game_id="connect4", game_version="1.0", match_id=match
    )


def make(ingest: FakeIngest, settings: Settings = SETTINGS) -> EventPublisher:
    return EventPublisher(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(ingest.handler)))


def test_el_evento_respeta_el_contrato_de_gamestats():
    e = to_gamestats_event(
        GameEvent("PLAYER_ACTION", "player", "DROP_DISC", {"column": 3}),
        game_id="connect4", game_version="1.0", match_id="connect4-abc",
    )
    for campo in ("eventId", "timestamp", "gameId", "gameVersion", "matchId", "type"):
        assert e[campo]
    assert RFC3339.match(e["timestamp"])
    assert (e["playerId"], e["action"], e["data"]) == ("player", "DROP_DISC", {"column": 3})
    ids = {to_gamestats_event(GameEvent("X"), game_id="g", game_version="1", match_id="m")["eventId"] for _ in range(100)}
    assert len(ids) == 100  # eventId único


def test_publish_no_bloquea_y_entrega_en_orden():
    async def run():
        ingest = FakeIngest()
        pub = make(ingest)
        for i in range(60):
            pub.publish("m1", [ev("m1", n=i)])
        assert pub.pending > 0  # publish() solo encola
        await pub.flush()
        assert [e["data"]["n"] for e in ingest.events] == list(range(60))
        assert pub.published == 60 and pub.pending == 0
        await pub.close()

    asyncio.run(run())


def test_partidas_concurrentes_no_se_mezclan():
    async def run():
        ingest = FakeIngest()
        pub = make(ingest)
        matches = [f"m{i}" for i in range(8)]

        async def play(m: str):
            for i in range(25):
                pub.publish(m, [ev(m, n=i)])
                await asyncio.sleep(0)

        await asyncio.gather(*(play(m) for m in matches))
        await pub.flush()
        for m in matches:
            mine = ingest.by_match(m)
            assert [e["data"]["n"] for e in mine] == list(range(25)), m
        assert len(ingest.events) == 8 * 25
        await pub.close()

    asyncio.run(run())


def test_reintenta_con_espera_cuando_gamestats_falla_y_no_pierde_eventos():
    async def run():
        ingest = FakeIngest()
        ingest.fail_next = 2  # los dos primeros intentos devuelven 503
        pub = make(ingest)
        pub.publish("m1", [ev("m1", n=1), ev("m1", "MATCH_FINISHED", n=2)])
        await pub.flush()
        assert len(ingest.events) == 2 and pub.retries == 2 and pub.dropped == 0
        await pub.close()

    asyncio.run(run())


def test_descarta_el_lote_tras_agotar_los_reintentos_sin_romper_nada():
    async def run():
        ingest = FakeIngest()
        ingest.fail_next = 999
        pub = make(ingest)
        pub.publish("m1", [ev("m1")])
        await pub.flush()
        assert pub.dropped == 1 and ingest.requests == SETTINGS.publish_max_attempts
        # y sigue funcionando para partidas nuevas cuando GameStats se recupera
        ingest.fail_next = 0
        pub.publish("m2", [ev("m2")])
        await pub.flush()
        assert len(ingest.by_match("m2")) == 1
        await pub.close()

    asyncio.run(run())


def test_error_de_conexion_tambien_se_reintenta():
    async def run():
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("sin conexión")
            return httpx.Response(202, json={"accepted": 1, "rejected": []})

        pub = EventPublisher(SETTINGS, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        pub.publish("m1", [ev("m1")])
        await pub.flush()
        assert pub.published == 1 and pub.retries == 2
        await pub.close()

    asyncio.run(run())


def test_rechazo_de_gamestats_no_se_reintenta():
    async def run():
        ingest = FakeIngest()
        ingest.status_override = 207
        pub = make(ingest)
        pub.publish("m1", [ev("m1")])
        await pub.flush()
        assert pub.rejected == 1 and pub.retries == 0 and ingest.requests == 1
        await pub.close()

    asyncio.run(run())
