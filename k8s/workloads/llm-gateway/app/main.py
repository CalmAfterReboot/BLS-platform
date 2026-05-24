from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from routers import completions
from middleware.auth import APIKeyMiddleware
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bls-gateway")

app = FastAPI(
    title="BLS LLM Gateway",
    description="Multi-provider LLM routing via LiteLLM",
    version="0.4.0",
)

Instrumentator().instrument(app).expose(app)

app.add_middleware(APIKeyMiddleware)
app.include_router(completions.router, prefix="/v1")

@app.get("/healthz")
async def health():
    return {"status": "ok", "service": "bls-llm-gateway"}
