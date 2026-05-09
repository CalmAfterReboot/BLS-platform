from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import os

VALID_KEYS = set(os.getenv("BLS_API_KEYS", "").split(","))

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/healthz", "/metrics", "/docs", "/openapi.json"]:
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = auth.removeprefix("Bearer ").strip()
        if token not in VALID_KEYS:
            raise HTTPException(status_code=403, detail="Invalid API key")
        return await call_next(request)
