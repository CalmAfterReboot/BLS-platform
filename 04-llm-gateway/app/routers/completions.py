from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import httpx
import logging
import os

router = APIRouter()
logger = logging.getLogger("bls-gateway")
LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm-service:4000")

class ChatRequest(BaseModel):
    model: str
    messages: list[dict]
    temperature: float = 0.7
    max_tokens: int = 1024
    stream: bool = False

@router.post("/chat/completions")
async def chat_completions(req: ChatRequest, request: Request):
    payload = req.model_dump()
    async with httpx.AsyncClient(timeout=130.0) as client:
        try:
            resp = await client.post(
                f"{LITELLM_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {os.getenv('LITELLM_MASTER_KEY', '')}"},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            logger.error(f"LiteLLM timeout for model {req.model}")
            raise HTTPException(status_code=504, detail="Backend timeout — model may be loading")
        except httpx.HTTPStatusError as e:
            logger.error(f"LiteLLM error: {e.response.status_code} {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
