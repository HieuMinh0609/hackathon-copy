"""Embedding chạy local qua Ollama."""
from __future__ import annotations

from config.settings import Settings


def get_embeddings(settings: Settings):
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(model=settings.embedding_model, base_url=settings.ollama_base_url)
