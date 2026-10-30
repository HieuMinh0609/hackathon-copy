"""ChromaDB lưu cục bộ tại data/chromadb."""
from __future__ import annotations

from config.settings import Settings
from backend.rag.embedder import get_embeddings


def get_vector_store(settings: Settings):
    from langchain_chroma import Chroma

    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=settings.collection_name,
        embedding_function=get_embeddings(settings),
        persist_directory=str(settings.chroma_dir),
    )


def reset_vector_store(settings: Settings) -> None:
    get_vector_store(settings).delete_collection()


def count_chunks(settings: Settings) -> int:
    return get_vector_store(settings)._collection.count()  # noqa: SLF001
