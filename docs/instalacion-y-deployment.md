# Instalación, ejecución y deployment

## Requisitos

- Docker Desktop encendido.
- Git.
- Python 3 (solo para la prueba de humo y las pruebas de la consola).
- Los repositorios `gameconsole` y `gamestats` en carpetas hermanas.

## Ejecutar

```powershell
git clone https://github.com/SeishiroGojo/gamestats.git
git clone https://github.com/SeishiroGojo/gameconsole.git
cd gameconsole
docker compose up -d --build --wait
```

- Consola: http://localhost:8000
- GameStats, ingestión (Go): http://localhost:8080 (`/health`, `/stats/live`)
- GameStats, análisis (Scala): http://localhost:8081 (`/stats/games`, `/stats/overall`)

Ver registros: `docker compose logs -f console`. Apagar: `docker compose down`. Con `-v` también se borra la base de datos de GameStats.

## Comprobar que todo funciona

```powershell
docker compose ps
python scripts/smoketest.py
```

`docker compose ps` debe mostrar los cuatro servicios como `healthy`. La prueba de humo juega seis partidas concurrentes en los tres juegos y comprueba que GameStats las reciba y las analice; debe terminar con `RESULTADO: todo correcto`.

## Ejecutar sin Docker (desarrollo)

```powershell
# terminal 1: Prolog (requiere SWI-Prolog instalado)
cd prolog
swipl -g main server.pl

# terminal 2: consola
cd console
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

En este modo hay que tener GameStats encendido por separado (ver el README de `gamestats`) y, si usa otros puertos, indicarlos con las variables `GAMESTATS_INGEST_URL`, `GAMESTATS_ANALYSIS_URL` y `PROLOG_URL`.

## Pipeline de CI/CD

| Job | Qué hace |
|---|---|
| `test-prolog` | Instala SWI-Prolog y corre las pruebas de la IA |
| `test-console` | Corre `pytest` y revisa la sintaxis del JavaScript |
| `e2e` | Clona GameStats, levanta todo con Docker Compose y ejecuta la prueba de humo |
| `publish` | Construye y publica las imágenes `gameconsole-console` y `gameconsole-prolog` en GHCR |
| `deploy` | Despliegue opcional por SSH (requiere la variable `DEPLOY_ENABLED=true` y los secretos del servidor) |

## Deployment con imágenes publicadas

Cuando el pipeline haya publicado las imágenes (y GameStats también), en cualquier máquina con Docker:

```powershell
docker compose -f docker-compose.deploy.yml pull
docker compose -f docker-compose.deploy.yml up -d
```

Variables opcionales en un archivo `.env`: `GHCR_OWNER`, `GAMECONSOLE_TAG`, `GAMESTATS_TAG`, `CONSOLE_PORT`. Los paquetes de GHCR deben estar en visibilidad pública para poder descargarse sin iniciar sesión.

## Problemas comunes

| Síntoma | Qué hacer |
|---|---|
| `port is already allocated` | Hay otro sistema usando 8000, 8080 u 8081. Ejecutar `docker compose down` en la carpeta del otro proyecto |
| Error de ruta al construir GameStats | Comprobar que `gamestats` está al lado de `gameconsole` |
| La etiqueta de GameStats está en rojo en la consola | Ver `docker compose logs go-ingestion` |
| Aparece "Prolog no respondió" | Ver `docker compose logs prolog`; al volver a estar disponible se usa el botón de reintentar |
