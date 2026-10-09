"""Ollama embedding client — local instance.

Thin async wrapper for generating vector embeddings via Ollama.
Uses shared httpx.AsyncClient for connection pooling.
"""

import httpx

from app.core.config import settings

# Shared client for connection pooling
_ollama_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _ollama_client
    if _ollama_client is None or _ollama_client.is_closed:
        _ollama_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=60, write=5, pool=3),
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
        )
    return _ollama_client


async def embed_text(text: str) -> list[float]:
    """Generate an embedding vector for the given text via Ollama.

    Returns a list of floats (the embedding).
    Raises on failure — callers should catch and handle.
    """
    client = _get_client()
    resp = await client.post(
        f"{settings.ollama_base_url}/api/embeddings",
        json={"model": settings.embedding_model, "prompt": text},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["embedding"]
