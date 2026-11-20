# Instalación, ejecución, CI/CD y deployment

## Orden recomendado (primera vez)

1. **GameStats v2** (repositorio `gamestats`): subir los cambios y esperar el ✅ del CI. Esto publica las imágenes `gamestats-ingestion` y `gamestats-analysis` con las estadísticas nuevas.
2. **GameConsole** (este repositorio): subir el código y esperar el ✅ del CI.

## Ejecutar localmente

```powershell
docker compose up -d --build --wait     # construye consola + Prolog y descarga GameStats
python scripts/smoketest.py             # prueba de punta a punta (opcional)
```

* Consola: http://localhost:8000
* GameStats ingestión: http://localhost:8080 (`/health`, `/stats/live`)
* GameStats análisis: http://localhost:8081 (`/stats/games`, `/stats/overall`)

Ver logs: `docker compose logs -f console`. Apagar: `docker compose down` (con `-v` borra también la base de datos).

### Sin Docker (desarrollo)

```powershell
# terminal 1 – Prolog (requiere SWI-Prolog instalado)
cd prolog ; swipl -g main server.pl
# terminal 2 – consola
cd console ; pip install -r requirements.txt ; python -m uvicorn app.main:app --port 8000
```

## Pipeline de CI/CD (`.github/workflows/ci.yml`)

| Job | Qué hace |
|---|---|
| `test-prolog` | Instala SWI-Prolog y corre las pruebas plunit |
| `test-console` | `pytest` (juegos, envío de eventos, API) y revisión del JavaScript |
| `e2e` | `docker compose up --build --wait` + `scripts/smoketest.py` con consola, Prolog y GameStats reales |
| `publish` | Construye y publica `gameconsole-console` y `gameconsole-prolog` en GHCR (`latest`, `sha-…`, `vX.Y.Z`) |
| `deploy` | Opcional por SSH (requiere `DEPLOY_ENABLED=true` y secretos) |

## Deployment (equivalente al de GameStats)

Con las imágenes publicadas por el CI, en cualquier máquina con Docker:

```powershell
docker compose -f docker-compose.deploy.yml pull
docker compose -f docker-compose.deploy.yml up -d
```

Abrir `http://<máquina>:8000`. Variables opcionales en un archivo `.env`: `GHCR_OWNER`, `GAMECONSOLE_TAG`, `GAMESTATS_TAG`, `CONSOLE_PORT`.

> Los paquetes de GHCR deben ser **públicos** (GitHub → perfil → *Packages* → paquete → *Package settings* → *Change visibility*), igual que en GameStats.

## Versiones

`git tag v1.0.0 && git push origin v1.0.0` publica además las imágenes con la etiqueta `1.0.0`.
