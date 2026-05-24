from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import os

VALID_KEYS = set(os.getenv("BLS_API_KEYS", "").split(","))


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/healthz", "/metrics", "/docs", "/openapi.json"]:
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                status_code=401, content={"detail": "Missing Bearer token"}
            )
        token = auth.removeprefix("Bearer ").strip()
        if token not in VALID_KEYS:
            return JSONResponse(
                status_code=403, content={"detail": "Invalid API key"}
            )
        return await call_next(request)
