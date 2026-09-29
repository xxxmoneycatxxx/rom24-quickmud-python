"""Unified server: single process running both telnet and WebSocket.

Shares one game loop, one world initialization, one SQLite connection.
Eliminates the concurrent-write risk of running two separate containers.

Usage:
    python -m mud unified
    python -m mud unified --telnet-port 5100 --ws-port 8000
"""
from __future__ import annotations

import asyncio
from typing import Any

import uvicorn

from mud.config import HOST, PORT, load_qmconfig
from mud.db.migrations import run_migrations
from mud.game_loop import async_game_loop
from mud.net.telnet_server import create_server
from mud.network.websocket_server import app, startup as ws_startup, shutdown as ws_shutdown
from mud.security import bans
from mud.world.world_state import initialize_world


async def _run_unified(telnet_port: int, ws_port: int) -> None:
    """Start telnet + WebSocket servers sharing one game loop."""
    # 1. Initialize world (once)
    load_qmconfig()
    run_migrations()
    initialize_world("area/area.lst")
    bans.load_bans_file()

    # Mark telnet server's create_server() to skip redundant init.
    import mud.net.telnet_server as _ts
    _ts._world_initialized = True

    # 2. Start single game loop
    game_task: Any = asyncio.create_task(async_game_loop())
    print("Game loop started (shared)")

    # 3. Start telnet server (no game loop creation)
    telnet_server = await create_server(host=HOST, port=telnet_port)
    sockets = getattr(telnet_server, "sockets", None)
    if sockets:
        addr = sockets[0].getsockname()
        print(f"Telnet serving on {addr}")

    # 4. Start WebSocket server (reuse game loop, skip world init)
    await ws_startup(game_task=game_task)
    print(f"WebSocket serving on {HOST}:{ws_port}")

    # 5. Run both servers concurrently
    uvicorn_config = uvicorn.Config(app, host=HOST, port=ws_port, log_level="warning")
    uvicorn_server = uvicorn.Server(uvicorn_config)

    try:
        await asyncio.gather(
            telnet_server.serve_forever(),
            uvicorn_server.serve(),
        )
    finally:
        game_task.cancel()
        try:
            await game_task
        except asyncio.CancelledError:
            print("Game loop stopped")
        await ws_shutdown()


def run(telnet_port: int = PORT, ws_port: int = 8000) -> None:
    """Entry point for `mud unified` CLI command."""
    print(f"Starting unified server (telnet:{telnet_port} ws:{ws_port})")
    asyncio.run(_run_unified(telnet_port=telnet_port, ws_port=ws_port))


if __name__ == "__main__":
    run()
