from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mud.config import CORS_ORIGINS, HOST, PORT, load_qmconfig
from mud.db.migrations import run_migrations
from mud.game_loop import async_game_loop
from mud.net.connection import handle_connection_with_stream
from mud.security import bans
from mud.world.world_state import initialize_world

from .websocket_stream import WebSocketStream

# Resolve web-client static directory relative to project root.
# websocket_server.py lives in mud/network/; project root is three levels up.
_WEB_CLIENT_DIR = Path(__file__).resolve().parent.parent.parent / "web-client"

_game_task = None


async def startup() -> None:
    global _game_task
    load_qmconfig()
    run_migrations()
    initialize_world("area/area.lst")
    bans.load_bans_file()
    # Start game loop as background task
    _game_task = asyncio.create_task(async_game_loop())
    print("🎮 Game loop started for WebSocket server")


async def shutdown() -> None:
    global _game_task
    if _game_task:
        _game_task.cancel()
        try:
            await _game_task
        except asyncio.CancelledError:
            print("Game loop stopped")
            pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    await startup()
    try:
        yield
    finally:
        await shutdown()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    stream = WebSocketStream(websocket)
    await handle_connection_with_stream(
        stream,
        host_for_ban=stream.peer_host,
        connection_type="WebSocket",
    )


# ── Static web-client files ───────────────────────────────────────────────
# Mounted at module level so the routes exist before uvicorn imports the app.
# The /ws WebSocket route above is registered first and takes priority.
if _WEB_CLIENT_DIR.is_dir():

    @app.get("/")
    async def _serve_index() -> FileResponse:
        return FileResponse(_WEB_CLIENT_DIR / "index.html", media_type="text/html")

    @app.get("/favicon.ico")
    async def _serve_favicon() -> FileResponse:
        favicon = _WEB_CLIENT_DIR / "favicon.svg"
        return FileResponse(favicon, media_type="image/svg+xml")

    app.mount("/_static", StaticFiles(directory=str(_WEB_CLIENT_DIR)), name="web-client")
    print(f"\U0001f310 Web client served from {_WEB_CLIENT_DIR}")
else:
    print(f"\u26a0\ufe0f  Web client directory not found: {_WEB_CLIENT_DIR}")


def run(host: str = HOST, port: int = PORT) -> None:
    uvicorn.run("mud.network.websocket_server:app", host=host, port=port)


if __name__ == "__main__":
    run()
