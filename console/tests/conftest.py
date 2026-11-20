import json
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.events import EventPublisher
from app.main import create_app


class FakeIngest:
    """GameStats (Go) de mentira: guarda los eventos que recibe."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.requests = 0
        self.fail_next = 0  # cuántas peticiones deben fallar con 503 antes de aceptar
        self.status_override: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/events":
            self.requests += 1
            if self.fail_next > 0:
                self.fail_next -= 1
                return httpx.Response(503, text="no disponible")
            if self.status_override:
                return httpx.Response(self.status_override, json={"accepted": 0, "rejected": ["x: inválido"]})
            batch = json.loads(request.content)
            self.events.extend(batch)
            return httpx.Response(202, json={"accepted": len(batch), "rejected": []})
        if request.url.path == "/stats/live":
            return httpx.Response(200, json={"totals": {"started": 1, "finished": 0, "active": 1, "events": 1}, "games": []})
        if request.url.path == "/stats/games":
            return httpx.Response(200, json=[])
        if request.url.path == "/stats/overall":
            return httpx.Response(200, json={"matches": 0})
        return httpx.Response(404)

    def by_match(self, match_id: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["matchId"] == match_id]


class FakeProlog:
    """Prolog de mentira: juega la primera columna con espacio (determinista)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = False

    async def best_move(self, request: dict[str, Any]):
        from app.prolog_client import PrologUnavailable

        self.calls.append(request)
        if self.fail:
            raise PrologUnavailable("Prolog caído (simulado)")
        board = request["board"]
        col = next(c for c in range(7) if board[0][c] == 0)
        return {"column": col, "score": 42, "nodes": 123, "depth": request["depth"], "candidates": []}, 7

    async def health(self) -> bool:
        return True

    async def close(self) -> None:
        pass


@pytest.fixture
def fast_settings() -> Settings:
    return Settings(publish_backoff_seconds=0.01, publish_max_attempts=4, idle_timeout_seconds=0.2,
                    finished_retention_seconds=0.2, bot_delay_seconds=0.0)


@pytest.fixture
def ingest() -> FakeIngest:
    return FakeIngest()


@pytest.fixture
def prolog() -> FakeProlog:
    return FakeProlog()


@pytest.fixture
def client(fast_settings, ingest, prolog):
    from fastapi.testclient import TestClient

    http = httpx.AsyncClient(transport=httpx.MockTransport(ingest.handler))
    publisher = EventPublisher(fast_settings, client=http)
    app = create_app(fast_settings, publisher=publisher, prolog=prolog, stats_client=http, start_reaper=False)
    with TestClient(app) as c:
        c.publisher = publisher
        c.registry = app.state.registry
        yield c
