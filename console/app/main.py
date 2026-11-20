"""Aplicación web de GameConsole (FastAPI).

Rutas:
    GET  /                          interfaz web (consola + panel de control)
    GET  /api/games                 catálogo de los tres juegos
    POST /api/matches               crea una instancia de juego
    GET  /api/matches               instancias de esta consola
    GET  /api/matches/{id}          estado de una instancia
    POST /api/matches/{id}/actions  jugada de la persona (y respuesta de la IA)
    POST /api/matches/{id}/ai       reintenta la jugada de la IA (Prolog)
    POST /api/matches/{id}/abandon  abandona la partida
    POST /api/demo/bots             lanza partidas automáticas (demostración de concurrencia)
    GET  /api/stats/all             estadísticas de GameStats para el panel (en vivo)
    GET  /health
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .bots import BotLauncher
from .config import Settings
from .events import EventPublisher, utc_now_iso
from .games import InvalidAction
from .prolog_client import PrologClient, PrologUnavailable
from .registry import MatchRegistry, UnknownGame

log = logging.getLogger("gameconsole")
STATIC_DIR = Path(__file__).parent / "static"


class CreateMatch(BaseModel):
    gameId: str
    options: dict[str, Any] = Field(default_factory=dict)


class BotRequest(BaseModel):
    perGame: int = Field(default=2, ge=1, le=10)


class StatsGateway:
    """Consulta a GameStats. Solo reenvía lo que GameStats responde: no calcula nada."""

    def __init__(self, settings: Settings, client: Optional[httpx.AsyncClient] = None) -> None:
        self._s = settings
        self._client = client or httpx.AsyncClient(timeout=3.0)
        self._owns = client is None

    async def _get(self, url: str) -> tuple[Optional[Any], Optional[str]]:
        try:
            resp = await self._client.get(url)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"HTTP {resp.status_code}"
        except (httpx.HTTPError, ValueError) as exc:
            return None, f"{type(exc).__name__}: {exc}"

    async def fetch_all(self) -> dict[str, Any]:
        (live, live_err), (games, games_err), (overall, overall_err) = await asyncio.gather(
            self._get(f"{self._s.ingest_url}/stats/live"),
            self._get(f"{self._s.analysis_url}/stats/games"),
            self._get(f"{self._s.analysis_url}/stats/overall"),
        )
        return {
            "fetchedAt": utc_now_iso(),
            "live": live,  # GameStats (Go): instancias iniciadas / en curso / terminadas, eventos por tipo
            "games": games,  # GameStats (Scala): estadísticas agregadas por juego
            "overall": overall,  # GameStats (Scala): estadísticas generales
            "sources": {
                "ingestion": {"ok": live_err is None, "error": live_err, "url": self._s.ingest_url},
                "analysis": {
                    "ok": games_err is None and overall_err is None,
                    "error": games_err or overall_err,
                    "url": self._s.analysis_url,
                },
            },
        }

    async def close(self) -> None:
        if self._owns:
            await self._client.aclose()


def create_app(
    settings: Optional[Settings] = None,
    publisher: Optional[EventPublisher] = None,
    prolog: Optional[PrologClient] = None,
    stats_client: Optional[httpx.AsyncClient] = None,
    start_reaper: bool = True,
) -> FastAPI:
    settings = settings or Settings.from_env()
    publisher = publisher or EventPublisher(settings)
    prolog = prolog or PrologClient(settings.prolog_url)
    registry = MatchRegistry(settings, publisher, prolog)
    gateway = StatsGateway(settings, stats_client)
    bots = BotLauncher(settings, registry)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def reaper() -> None:
            while True:
                await asyncio.sleep(max(1.0, min(30.0, settings.idle_timeout_seconds / 4)))
                try:
                    await registry.reap_once()
                except Exception:  # pragma: no cover - el reaper nunca debe morir
                    log.exception("error en el reaper de partidas")

        task = asyncio.create_task(reaper()) if start_reaper else None
        yield
        if task:
            task.cancel()
        bots.cancel_all()
        # Cierre ordenado: se abandonan las partidas en curso para que GameStats las dé por cerradas.
        for s in registry.all():
            await s.abandon()
        await publisher.close()
        await prolog.close()
        await gateway.close()

    app = FastAPI(title="GameConsole", version="1.0.0", lifespan=lifespan)
    app.state.registry = registry
    app.state.publisher = publisher

    def get_session(match_id: str):
        s = registry.get(match_id)
        if s is None:
            raise HTTPException(404, f"no existe la partida {match_id}")
        return s

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "prolog": await prolog.health(), "publisher": publisher.stats()}

    @app.get("/api/games")
    async def games() -> list[dict[str, Any]]:
        return registry.catalog()

    @app.post("/api/matches", status_code=201)
    async def create_match(body: CreateMatch) -> dict[str, Any]:
        try:
            session = registry.create(body.gameId, body.options)
        except UnknownGame:
            raise HTTPException(404, f"juego desconocido: {body.gameId}")
        except InvalidAction as exc:
            raise HTTPException(400, str(exc))
        return session.describe()

    @app.get("/api/matches")
    async def list_matches() -> list[dict[str, Any]]:
        return [s.describe() for s in registry.all()]

    @app.get("/api/matches/{match_id}")
    async def get_match(match_id: str) -> dict[str, Any]:
        return get_session(match_id).describe()

    @app.post("/api/matches/{match_id}/actions")
    async def play(match_id: str, action: dict[str, Any]):
        session = get_session(match_id)
        try:
            await session.act(action)
        except InvalidAction as exc:
            raise HTTPException(400, str(exc))
        except PrologUnavailable as exc:
            # La jugada de la persona ya se aplicó; la IA quedó pendiente y se puede reintentar.
            return JSONResponse(status_code=503, content={"error": str(exc), "match": session.describe()})
        return session.describe()

    @app.post("/api/matches/{match_id}/ai")
    async def retry_ai(match_id: str):
        session = get_session(match_id)
        try:
            await session.retry_ai()
        except InvalidAction as exc:
            raise HTTPException(400, str(exc))
        except PrologUnavailable as exc:
            return JSONResponse(status_code=503, content={"error": str(exc), "match": session.describe()})
        return session.describe()

    @app.post("/api/matches/{match_id}/abandon")
    async def abandon(match_id: str) -> dict[str, Any]:
        session = get_session(match_id)
        await session.abandon()
        return session.describe()

    @app.post("/api/demo/bots", status_code=202)
    async def launch_bots(body: BotRequest) -> dict[str, Any]:
        """Lanza partidas automáticas (una por bot) de los tres juegos, para demostrar la concurrencia."""
        launched = bots.launch(body.perGame)
        if not launched:
            raise HTTPException(429, "Ya hay demasiadas partidas automáticas en curso")
        return {"launched": len(launched), "matchIds": launched, "running": bots.running}

    @app.get("/api/stats/all")
    async def stats_all() -> dict[str, Any]:
        data = await gateway.fetch_all()
        data["console"] = {"instances": registry.summary(), "publisher": publisher.stats()}
        return data

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})

    return app


app = create_app()
