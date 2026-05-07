"""HTTP + WebSocket hotload server.

Endpoints (all on the same port):
    GET  /health                              → { "ok": true }
    GET  /config                              → effective config (debug)
    GET  /{platform}/layout/{layout_name}     → resolved flat JSON
    WS   {ws_path}                            → push file-change events

WebSocket protocol:
    client → server: { "type": "hello", "platform": "ios" | "android" }
    server → client: { "type": "welcome", "serverVersion": "1.0.0",
                       "supportedPlatforms": ["ios", "android"] }
    server → client: { "type": "hello_ack", "platform": "ios" }
    server → client: { "type": "layout_changed",
                       "platform": "ios",
                       "kind": "modified" | "created" | "deleted",
                       "layout": "home/home_header",
                       "path": "/ios/layout/home/home_header" }
    server → client: { "type": "style_changed",
                       "platform": "ios",
                       "kind": "...",
                       "style": "card" }
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from .config_loader import HotloadConfig
from .layout_resolver import LayoutResolver
from .platform_filter import VALID_PLATFORMS
from .watcher import FileChange, LayoutWatcher


SUPPORTED_PLATFORMS = ("ios", "android")  # web is build-step only
SERVER_VERSION = "1.0.0"

logger = logging.getLogger("jui.hotload")


class HotloadServer:
    def __init__(self, config: HotloadConfig):
        self._config = config
        self._resolver = LayoutResolver(
            layouts_dir=config.layouts_dir,
            styles_dir=config.styles_dir,
        )
        self._clients: set[_Client] = set()
        self._watcher: LayoutWatcher | None = None
        self._watch_task: asyncio.Task | None = None
        self._http_runner: web.AppRunner | None = None

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        self._watcher = LayoutWatcher(
            paths=self._config.watch_paths,
            ignored=self._config.ignored_patterns,
            loop=loop,
        )
        self._watcher.start()
        self._watch_task = asyncio.create_task(self._consume_file_changes())

        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_get("/config", self._debug_config)
        app.router.add_get(self._config.ws_path, self._ws_handler)
        app.router.add_get(
            "/{platform}/layout/{layout_name:.+}",
            self._http_layout,
        )

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self._config.host, self._config.port)
        await site.start()
        self._http_runner = runner

        logger.info(
            "jui hotload listening: http://%s:%d   ws://%s:%d%s",
            self._config.host,
            self._config.port,
            self._config.host,
            self._config.port,
            self._config.ws_path,
        )
        logger.info("client IP hint: %s", self._config.resolve_client_ip())
        logger.info("watching: %s", ", ".join(str(p) for p in self._config.watch_paths))

        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass
        finally:
            await self._shutdown()

    async def _shutdown(self) -> None:
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        if self._watcher:
            self._watcher.stop()
        for client in list(self._clients):
            try:
                await client.ws.close()
            except Exception:  # noqa: BLE001
                pass
        if self._http_runner:
            await self._http_runner.cleanup()

    # ─── HTTP handlers ─────────────────────────────────────────────────

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "version": SERVER_VERSION})

    async def _debug_config(self, request: web.Request) -> web.Response:
        return web.json_response({
            "host": self._config.host,
            "port": self._config.port,
            "wsPath": self._config.ws_path,
            "clientIp": self._config.resolve_client_ip(),
            "layoutsDir": str(self._config.layouts_dir),
            "stylesDir": str(self._config.styles_dir),
            "watchPaths": [str(p) for p in self._config.watch_paths],
        })

    async def _http_layout(self, request: web.Request) -> web.Response:
        platform = request.match_info["platform"]
        layout_name = request.match_info["layout_name"]
        if layout_name.endswith(".json"):
            layout_name = layout_name[:-5]

        if platform not in SUPPORTED_PLATFORMS:
            return web.json_response(
                {"error": f"unsupported platform: {platform}"},
                status=400,
            )

        resolved = self._resolver.resolve(layout_name, platform)
        if resolved is None:
            return web.json_response(
                {"error": f"layout not found: {layout_name}"},
                status=404,
            )
        return web.json_response(resolved)

    # ─── WebSocket ─────────────────────────────────────────────────────

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        client = _Client(ws)
        self._clients.add(client)
        try:
            await ws.send_json({
                "type": "welcome",
                "serverVersion": SERVER_VERSION,
                "supportedPlatforms": list(SUPPORTED_PLATFORMS),
            })
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_ws_text(client, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    logger.warning("WS connection error: %s", ws.exception())
                    break
        finally:
            self._clients.discard(client)
        return ws

    async def _handle_ws_text(self, client: "_Client", data: str) -> None:
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return
        if msg.get("type") != "hello":
            return
        platform = msg.get("platform")
        if platform in SUPPORTED_PLATFORMS:
            client.platform = platform
            await _safe_send(client.ws, {
                "type": "hello_ack",
                "platform": platform,
            })
        else:
            await _safe_send(client.ws, {
                "type": "error",
                "reason": f"unsupported platform: {platform}",
            })

    # ─── file change consumer ─────────────────────────────────────────

    async def _consume_file_changes(self) -> None:
        assert self._watcher is not None
        queue = self._watcher.queue
        while True:
            change = await queue.get()
            try:
                await self._dispatch_change(change)
            except Exception as exc:  # noqa: BLE001
                logger.exception("failed to dispatch change %s: %s", change, exc)

    async def _dispatch_change(self, change: FileChange) -> None:
        layouts_dir = self._config.layouts_dir
        styles_dir = self._config.styles_dir
        abs_path = change.path.resolve()

        layout_name = self._resolver.layout_name_for_path(abs_path)
        if layout_name is not None:
            # A style change may have invalidated caches too; but for a
            # plain layout change we don't need to wipe style caches.
            await self._broadcast_layout(change.kind, layout_name)
            return

        if self._is_under(abs_path, styles_dir):
            rel = abs_path.relative_to(styles_dir)
            if rel.suffix == ".json":
                style_name = str(rel.with_suffix("")).replace("\\", "/")
                # Styles are shared across layouts — wipe cache for this
                # style so next layout fetch re-reads from disk.
                self._resolver.invalidate_styles(style_name)
                await self._broadcast_style(change.kind, style_name)

    async def _broadcast_layout(self, kind: str, layout_name: str) -> None:
        for client in list(self._clients):
            if client.platform not in SUPPORTED_PLATFORMS:
                continue
            payload: dict[str, Any] = {
                "type": "layout_changed",
                "platform": client.platform,
                "kind": kind,
                "layout": layout_name,
                "path": f"/{client.platform}/layout/{layout_name}",
            }
            await _safe_send(client.ws, payload)

    async def _broadcast_style(self, kind: str, style_name: str) -> None:
        for client in list(self._clients):
            if client.platform not in SUPPORTED_PLATFORMS:
                continue
            payload: dict[str, Any] = {
                "type": "style_changed",
                "platform": client.platform,
                "kind": kind,
                "style": style_name,
            }
            await _safe_send(client.ws, payload)

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False


class _Client:
    __slots__ = ("ws", "platform")

    def __init__(self, ws: web.WebSocketResponse):
        self.ws = ws
        self.platform: str | None = None

    def __hash__(self) -> int:
        return id(self)


async def _safe_send(ws: web.WebSocketResponse, payload: dict[str, Any]) -> None:
    try:
        await ws.send_json(payload)
    except (ConnectionResetError, RuntimeError):
        pass


def run_server(config: HotloadConfig) -> None:
    """Blocking entry point — starts the asyncio loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    server = HotloadServer(config)
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("received interrupt, shutting down")
