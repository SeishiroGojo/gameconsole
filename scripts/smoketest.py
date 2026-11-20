#!/usr/bin/env python3
"""Prueba de humo de punta a punta de GameConsole (solo biblioteca estándar).

Con todo el sistema levantado (docker compose up), juega varias partidas
concurrentes en los tres juegos a través de la API de la consola y comprueba que:
  * la IA de Prolog responde (Conecta 4),
  * GameStats recibe los eventos (contadores en vivo),
  * GameStats analiza las partidas terminadas (estadísticas por juego y generales).

Uso:  python scripts/smoketest.py [URL_DE_LA_CONSOLA]      (por defecto http://localhost:8000)
"""
import json
import sys
import threading
import time
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
failures: list[str] = []


def call(method: str, path: str, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def check(ok: bool, text: str) -> None:
    print(("  [OK]   " if ok else "  [FALLO] ") + text)
    if not ok:
        failures.append(text)


def wait_for(cond, seconds=40.0, every=0.5):
    end = time.time() + seconds
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(every)
    return None


def play_connect4(n: int, out: dict):
    _, m = call("POST", "/api/matches", {"gameId": "connect4", "options": {"difficulty": "easy"}})
    for col in (3, 2, 4, 3, 1):
        legal = [c for c in range(7) if m["state"]["board"][0][c] == 0]
        status, m2 = call("POST", f"/api/matches/{m['matchId']}/actions", {"type": "drop", "column": col if col in legal else legal[0]})
        if status != 200:
            out[f"c4-{n}"] = (status, m2)
            return
        m = m2
        if m["status"] == "finished":
            break
    if m["status"] != "finished":
        _, m = call("POST", f"/api/matches/{m['matchId']}/abandon")
    out[f"c4-{n}"] = (200, m)


def play_2048(n: int, out: dict):
    _, m = call("POST", "/api/matches", {"gameId": "game-2048"})
    for d in ("left", "down", "right", "up") * 3:
        call("POST", f"/api/matches/{m['matchId']}/actions", {"type": "move", "direction": d})
    _, m = call("POST", f"/api/matches/{m['matchId']}/abandon")
    out[f"2048-{n}"] = (200, m)


def play_mines(n: int, out: dict):
    _, m = call("POST", "/api/matches", {"gameId": "minesweeper"})
    call("POST", f"/api/matches/{m['matchId']}/actions", {"type": "reveal", "row": 4, "col": 4})
    _, m = call("POST", f"/api/matches/{m['matchId']}/abandon")
    out[f"mines-{n}"] = (200, m)


print(f"== Prueba de humo de GameConsole en {BASE}")
print("== 1. Servicios")
ok = wait_for(lambda: call("GET", "/health")[1].get("prolog") is True, 60)
check(bool(ok), "la consola responde y Prolog está disponible")

print("== 2. Seis partidas concurrentes (2 por juego)")
results: dict = {}
threads = [threading.Thread(target=f, args=(i, results)) for i in range(2) for f in (play_connect4, play_2048, play_mines)]
[t.start() for t in threads]
[t.join() for t in threads]
check(len(results) == 6 and all(s == 200 for s, _ in results.values()), "las 6 partidas se jugaron sin errores")
ids = {m["matchId"] for _, m in results.values()}
check(len(ids) == 6, "cada instancia tiene un matchId distinto")
c4 = [m for k, (_, m) in results.items() if k.startswith("c4")]
check(all(m["state"]["aiInfo"] is not None for m in c4), "la IA (Prolog) jugó en las partidas de Conecta 4")

print("== 3. GameStats recibió y analizó los eventos")
def stats():
    s, d = call("GET", "/api/stats/all")
    return d if s == 200 else None

def listo():
    d = stats()
    if not d or not d["sources"]["ingestion"]["ok"] or not d["sources"]["analysis"]["ok"]:
        return None
    return d if (d["overall"] or {}).get("matches", 0) >= 6 else None

d = wait_for(listo, 45)
check(d is not None, "GameStats analizó las 6 partidas terminadas")
if d:
    games = {g["gameId"]: g for g in d["games"]}
    check(set(games) >= {"connect4", "game-2048", "minesweeper"}, "estadísticas por juego para los tres juegos")
    live = {g["gameId"]: g for g in d["live"]["games"]}
    check(all(live[g]["started"] >= 2 and live[g]["finished"] >= 2 for g in ("connect4", "game-2048", "minesweeper")),
          "contadores de instancias en vivo (iniciadas y terminadas) por juego")
    check(d["live"]["totals"]["active"] >= 0 and d["overall"]["matches"] >= 6, "estadísticas generales presentes")
    check(d["console"]["publisher"]["dropped"] == 0, "no se descartó ningún evento")

print()
if failures:
    print(f"RESULTADO: {len(failures)} comprobación(es) fallaron")
    sys.exit(1)
print("RESULTADO: todo correcto")
