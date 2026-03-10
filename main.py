from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import AppSettings, load_settings
from routes import api_router, gui_router
from services.reader_manager import ReaderManager
from services.readers import build_reader
from services.websocket_manager import WebSocketManager
from storage.database import Database


PROJECT_ROOT = Path(__file__).resolve().parent
SETTINGS = load_settings(PROJECT_ROOT)


def configure_logging(settings: AppSettings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(SETTINGS)
    logger = logging.getLogger(__name__)
    logger.info("Booting local RFID service from %s", PROJECT_ROOT)

    database = Database(SETTINGS.database_path)
    await database.initialize()

    websocket_manager = WebSocketManager()
    readers = [build_reader(reader_settings) for reader_settings in SETTINGS.readers]
    reader_manager = ReaderManager(readers=readers, database=database, websocket_manager=websocket_manager)

    app.state.settings = SETTINGS
    app.state.database = database
    app.state.websocket_manager = websocket_manager
    app.state.reader_manager = reader_manager
    app.state.templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))

    await reader_manager.start()

    try:
        yield
    finally:
        await reader_manager.stop()
        await database.close()
        logger.info("Local RFID service stopped.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Raspberry Pi RFID Local MVP",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
    app.include_router(gui_router)
    app.include_router(api_router)
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("main:app", host=SETTINGS.host, port=SETTINGS.port, reload=False)
