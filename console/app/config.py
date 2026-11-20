"""Configuración por variables de entorno (valores por defecto para desarrollo local)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    #: Servicio de ingestión de GameStats (Go): recibe los eventos y expone /stats/live.
    ingest_url: str = "http://localhost:8080"
    #: Servicio de análisis de GameStats (Scala): expone /stats/games y /stats/overall.
    analysis_url: str = "http://localhost:8081"
    #: Servicio Prolog con la IA de Conecta 4.
    prolog_url: str = "http://localhost:8090"
    #: Una partida sin actividad durante este tiempo se da por abandonada.
    idle_timeout_seconds: float = 180.0
    #: Cuánto tiempo se conserva una partida terminada para poder consultarla.
    finished_retention_seconds: float = 600.0
    #: Reintentos de envío de eventos y pausa inicial (se duplica en cada intento).
    publish_max_attempts: int = 6
    publish_backoff_seconds: float = 0.5
    publish_timeout_seconds: float = 5.0
    #: Pausa entre jugadas de las partidas automáticas de demostración.
    bot_delay_seconds: float = 0.6
    #: Máximo de partidas automáticas simultáneas.
    bot_max_concurrent: int = 40

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            ingest_url=os.environ.get("GAMESTATS_INGEST_URL", cls.ingest_url).rstrip("/"),
            analysis_url=os.environ.get("GAMESTATS_ANALYSIS_URL", cls.analysis_url).rstrip("/"),
            prolog_url=os.environ.get("PROLOG_URL", cls.prolog_url).rstrip("/"),
            idle_timeout_seconds=_float("IDLE_TIMEOUT_SECONDS", cls.idle_timeout_seconds),
            finished_retention_seconds=_float("FINISHED_RETENTION_SECONDS", cls.finished_retention_seconds),
            publish_max_attempts=_int("PUBLISH_MAX_ATTEMPTS", cls.publish_max_attempts),
            publish_backoff_seconds=_float("PUBLISH_BACKOFF_SECONDS", cls.publish_backoff_seconds),
            publish_timeout_seconds=_float("PUBLISH_TIMEOUT_SECONDS", cls.publish_timeout_seconds),
            bot_delay_seconds=_float("BOT_DELAY_SECONDS", cls.bot_delay_seconds),
            bot_max_concurrent=_int("BOT_MAX_CONCURRENT", cls.bot_max_concurrent),
        )
