"""Cliente del servicio Prolog (prolog/server.pl): le envía el tablero y recibe la jugada."""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx


class PrologUnavailable(Exception):
    """El servicio Prolog no respondió o devolvió un error."""


class PrologClient:
    def __init__(self, base_url: str, client: Optional[httpx.AsyncClient] = None, retries: int = 2) -> None:
        self._base = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=20.0)
        self._owns_client = client is None
        self._retries = retries

    async def best_move(self, request: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """Pide una jugada. Devuelve (respuesta de Prolog, latencia en ms)."""
        last: Optional[Exception] = None
        for _ in range(self._retries + 1):
            started = time.perf_counter()
            try:
                resp = await self._client.post(f"{self._base}/move", json=request)
                if resp.status_code == 200:
                    return resp.json(), int((time.perf_counter() - started) * 1000)
                last = PrologUnavailable(f"Prolog respondió {resp.status_code}: {resp.text[:200]}")
            except httpx.HTTPError as exc:
                last = PrologUnavailable(f"no se pudo contactar a Prolog: {exc}")
        assert last is not None
        raise last

    async def health(self) -> bool:
        try:
            resp = await self._client.get(f"{self._base}/health", timeout=3.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
