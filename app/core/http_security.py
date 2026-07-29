"""Scoped HTTP response security policies."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

PRIVATE_NO_STORE = "private, no-store"
_WORKSPACE_API_PREFIX = "/api/v1/workspaces/"
_CONNECTORS_PATH_SEGMENT = "/connectors"


class ConnectorResponseNoStoreMiddleware:
    """Prevent caching for every workspace connector response.

    Applying the policy at the ASGI boundary also covers responses created
    before endpoint execution, including authentication, authorization and
    request-validation failures.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        path = str(scope.get("path", ""))
        protect_response = bool(
            scope.get("type") == "http"
            and path.startswith(_WORKSPACE_API_PREFIX)
            and _CONNECTORS_PATH_SEGMENT in path
        )
        if not protect_response:
            await self._app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = PRIVATE_NO_STORE
            await send(message)

        await self._app(scope, receive, send_wrapper)
