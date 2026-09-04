"""
Local embeddings for semantic memory recall.

Optional by design, mirroring learning/neural_command_model.py's
torch-optional pattern: if the configured embedding model isn't pulled in
Ollama, every function here returns None/[] and callers fall back to their
existing keyword-based recall. Never a hard dependency.
"""

import struct
from typing import List, Optional

import requests
from loguru import logger

DEFAULT_MODEL = "nomic-embed-text"


def embed(
    text: str,
    host: str = "http://127.0.0.1:11434",
    model: str = DEFAULT_MODEL,
    timeout: float = 10.0,
    keep_alive: str = "30m",
) -> Optional[List[float]]:
    """Return an embedding vector for `text`, or None if unavailable.

    Never raises - a missing/unpulled model, a down Ollama server, or a
    malformed response all just mean "no embedding today", not a crash.

    `keep_alive` is required, not optional: without it Ollama evicts the
    embedding model after each request and reloads it on the next one,
    which measured 2.04s per call versus 0.047s with it - a 43x difference
    on a call that sits on the per-command path.
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        response = requests.post(
            f"{host}/api/embeddings",
            json={
                "model": model,
                "prompt": text,
                "keep_alive": keep_alive,
                # Pinned to CPU. This model is small enough that CPU
                # embedding is fast, and on a 4GB card keeping it resident
                # on the GPU evicted the language model - so every command
                # paid a 6 second reload to answer the NEXT one. Two models
                # both trying to stay resident is worse than one of them
                # being slightly slower.
                "options": {"num_gpu": 0},
            },
            timeout=timeout,
        )
        if response.status_code != 200:
            return None
        embedding = response.json().get("embedding")
        if not isinstance(embedding, list) or not embedding:
            return None
        return [float(v) for v in embedding]
    except Exception as exc:
        logger.debug("Embedding unavailable ({}): {}", model, str(exc)[:100])
        return None


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity of two equal-length vectors. Returns 0.0 on mismatch."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def pack_embedding(vector: List[float]) -> bytes:
    """Serialize a float vector to bytes for SQLite BLOB storage."""
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack_embedding(blob: bytes) -> List[float]:
    """Deserialize a float vector previously packed with pack_embedding."""
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob))
