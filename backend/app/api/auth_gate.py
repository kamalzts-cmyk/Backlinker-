"""Shared-secret gate for public deployments.

This project has no real auth/`projects` layer (see
docs/ARCHITECTURE.md §9) -- every route is otherwise open to whoever
can reach it. That's fine for local dev, but the moment this API is
reachable from the public internet it means anyone can run the
crawler against arbitrary sites, harvest the contacts it finds, and
(if ANTHROPIC_API_KEY is set) spend against that key. This middleware
is a deliberately minimal bolt-on for exactly that case: one shared
secret, checked on every request, not a real multi-user session system.

Enforcement is opt-in via `settings.app_shared_secret`. Unset (the
default -- every local dev/test run), it's a no-op. Set it before
deploying publicly.
"""

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings

HEADER_NAME = "x-app-secret"


class SharedSecretMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        secret = settings.app_shared_secret
        if not secret:
            return await call_next(request)

        provided = request.headers.get(HEADER_NAME, "")
        if not hmac.compare_digest(provided, secret):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "unauthorized",
                        "message": "Missing or invalid shared secret.",
                        "detail": None,
                    }
                },
            )
        return await call_next(request)
