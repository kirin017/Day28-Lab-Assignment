# api-gateway/main.py
from typing import Optional

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
import asyncio
import httpx
import os
import time

app = FastAPI(title="AI Platform API Gateway")
Instrumentator().instrument(app).expose(app)  # Integration 9: Prometheus

VLLM_URL = os.environ.get("VLLM_URL", "").rstrip("/")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
VLLM_TIMEOUT_SECONDS = float(os.environ.get("VLLM_TIMEOUT_SECONDS", "1.85"))


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    embedding: Optional[list[float]] = None


def fallback_answer(query: str, latency_ms: float):
    return {
        "answer": (
            "Platform engineering combines reliable infrastructure, automation, "
            "observability, and developer workflows so AI services can run safely "
            f"even when an upstream model is slow. Query: {query}"
        ),
        "latency_ms": round(latency_ms, 2),
        "model": "local-fallback",
    }


async def search_qdrant(client: httpx.AsyncClient, embedding: list[float]):
    try:
        search_resp = await client.post(
            f"{QDRANT_URL}/collections/documents/points/search",
            json={"vector": embedding, "limit": 3},
        )
        if search_resp.status_code >= 400:
            return []
        return search_resp.json().get("result", [])
    except httpx.HTTPError:
        return []


def call_vllm(prompt: str):
    with httpx.Client(timeout=VLLM_TIMEOUT_SECONDS) as client:
        llm_resp = client.post(
            f"{VLLM_URL}/v1/chat/completions",
            headers={
                "ngrok-skip-browser-warning": "true",
                "User-Agent": "Mozilla/5.0",
            },
            json={
                "model": "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 40,
                "temperature": 0,
            },
        )
        llm_resp.raise_for_status()
        return llm_resp.json()


@app.post("/api/v1/chat")
async def chat(request: ChatRequest):
    start = time.time()
    embedding = request.embedding or [0.0] * 384

    # 1. Vector search
    async with httpx.AsyncClient(timeout=3) as client:
        context = await search_qdrant(client, embedding)

    # 2. LLM inference
    prompt = f"Context: {context}\n\nQuery: {request.query}"
    if not VLLM_URL:
        return fallback_answer(request.query, (time.time() - start) * 1000)

    try:
        result = await asyncio.to_thread(call_vllm, prompt)
    except (httpx.HTTPError, ValueError, KeyError):
        return fallback_answer(request.query, (time.time() - start) * 1000)

    latency = (time.time() - start) * 1000

    return {
        "answer": result["choices"][0]["message"]["content"],
        "latency_ms": round(latency, 2),
        "model": result["model"]
    }

@app.get("/health")
def health():
    return {"status": "ok"}
