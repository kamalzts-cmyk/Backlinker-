"""Shared error shape per docs/API.md §Conventions:
`{"error": {"code", "message", "detail"}}` on every error response.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class NotFoundError(Exception):
    def __init__(self, message: str):
        self.message = message


class UpstreamServiceError(Exception):
    """A real external dependency (e.g. the AnthropicSearchProvider's
    API call) failed. Distinct from NotFoundError -- 502, not 404 --
    since nothing about the request was wrong, the upstream call was.
    """

    def __init__(self, message: str):
        self.message = message


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": exc.message, "detail": None}},
        )

    @app.exception_handler(UpstreamServiceError)
    async def _upstream_error(request: Request, exc: UpstreamServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "upstream_error", "message": exc.message, "detail": None}},
        )
