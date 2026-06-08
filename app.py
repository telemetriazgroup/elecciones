"""Dashboard ONPE — segunda vuelta con polling continuo."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fetcher import ElectionStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("onpe-dashboard")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
STATIC_DIR = Path(__file__).parent / "static"

store = ElectionStore(data_dir=DATA_DIR)
_poll_task: asyncio.Task | None = None


async def poll_loop() -> None:
    while True:
        try:
            await store.refresh()
        except Exception as exc:
            logger.error("Poll fallido: %s", exc)
        await asyncio.sleep(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _poll_task
    logger.info("Iniciando polling cada %s segundos", POLL_INTERVAL)
    await store.refresh()
    _poll_task = asyncio.create_task(poll_loop())
    yield
    if _poll_task:
        _poll_task.cancel()
        try:
            await _poll_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Dashboard ONPE Segunda Vuelta",
    description="Resultados electorales por departamento con actualización automática",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/data")
async def api_data():
    return store.to_api_dict(poll_interval_seconds=POLL_INTERVAL)


@app.get("/api/health")
async def health():
    s = store.snapshot
    return {
        "status": "ok" if not s.last_error else "degraded",
        "fetching": s.fetching,
        "updated_at": s.updated_at,
        "fetch_count": s.fetch_count,
        "poll_interval_seconds": POLL_INTERVAL,
        "last_error": s.last_error,
    }


@app.get("/api/historial")
async def api_historial(limit: int = 100):
    return {
        "state": store.history.get_state(),
        "entries": store.history.list_entries(limit=min(limit, 500)),
    }


@app.post("/api/refresh")
async def manual_refresh():
    snapshot = await store.refresh()
    return {"ok": True, "updated_at": snapshot.updated_at}
