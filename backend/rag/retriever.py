"""Truy xuất tài liệu đa ngôn ngữ (VI/EN/KR) từ ChromaDB cho bước suy luận LLM."""
from __future__ import annotations

from typing import Any, Sequence
from langchain_core.documents import Document

from config.settings import Settings
from backend.rag import vector_store


def _get_store(settings: Settings):
    return vector_store.get_vector_store(settings)


def _build_filter(settings: Settings, project_code: str | None = None) -> dict[str, Any] | None:
    """Xây dựng bộ lọc metadata kết hợp giữa project_code và role_filter."""
    filters: list[dict[str, Any]] = []
    if project_code:
        filters.append({"project_code": project_code})
    if getattr(settings, "role_filter", None):
        filters.append({"role": {"$in": settings.role_filter}})

    if len(filters) == 1:
        return filters[0]
    if len(filters) > 1:
        return {"$and": filters}
    return None


def retrieve(
    settings: Settings,
    query: str,
    k: int | None = None,
    project_code: str | None = None,
) -> list[Document]:
    """Tìm kiếm tương đồng ngữ nghĩa trong ChromaDB, lọc theo vai trò và dự án (project_code)."""
    store = _get_store(settings)
    target_k = k or settings.top_k
    meta_filter = _build_filter(settings, project_code=project_code)

    try:
        if meta_filter:
            results = store.similarity_search(query, k=target_k, filter=meta_filter)
            if results:
                return results
    except Exception:
        pass

    # Không được nới bộ lọc khi đã chỉ định dự án: tránh rò tài liệu khác role/dự án.
    if project_code:
        return []

    # Chỉ tìm kiếm toàn cục cho truy vấn không gắn dự án.
    try:
        return store.similarity_search(query, k=target_k)
    except Exception:
        return []


def retrieve_with_scores(
    settings: Settings,
    query: str,
    k: int | None = None,
    score_threshold: float | None = None,
    project_code: str | None = None,
) -> list[tuple[Document, float]]:
    """Truy xuất tài liệu kèm điểm tương đồng (similarity/relevance score), lọc theo mã dự án."""
    store = _get_store(settings)
    target_k = k or settings.top_k
    meta_filter = _build_filter(settings, project_code=project_code)

    raw_results: list[tuple[Document, float]] = []
    try:
        raw_results = store.similarity_search_with_relevance_scores(
            query, k=target_k, filter=meta_filter
        )
    except Exception:
        try:
            raw_results = store.similarity_search_with_score(
                query, k=target_k, filter=meta_filter
            )
        except Exception:
            try:
                raw_results = store.similarity_search_with_score(query, k=target_k)
            except Exception:
                return []

    if score_threshold is None:
        return raw_results

    # Lọc tài liệu theo ngưỡng liên quan
    filtered: list[tuple[Document, float]] = []
    for doc, score in raw_results:
        if score >= score_threshold:
            filtered.append((doc, score))
    return filtered


def format_multilingual_context(
    docs: Sequence[Document | tuple[Document, float]],
) -> str:
    """Định dạng context rõ ràng cho LLM (Qwen-2.5) đọc hiểu chéo tài liệu gốc (VI/EN/KR) và trả lời Tiếng Việt."""
    if not docs:
        return ""

    blocks: list[str] = []
    for idx, item in enumerate(docs, start=1):
        if isinstance(item, tuple):
            doc, score = item
            score_tag = f" | Độ tương đồng: {score:.2f}"
        else:
            doc = item
            score_tag = ""

        src = doc.metadata.get("source", "Không rõ")
        page = doc.metadata.get("page")
        file_type = doc.metadata.get("file_type", "doc")
        role = doc.metadata.get("role", "chung")

        header_parts = [f"Nguồn: {src}"]
        if page:
            header_parts.append(f"Trang {page}")
        header_parts.append(f"Loại: {file_type.upper()}")
        header_parts.append(f"Nhóm: {role}")

        header = f"[{idx}] (" + " | ".join(header_parts) + f"{score_tag})"
        blocks.append(f"{header}\n{doc.page_content.strip()}")

    return "\n\n".join(blocks)


def retrieve_by_project(
    settings: Settings,
    project_code: str,
    query: str,
    k: int | None = None,
) -> list[Document]:
    """Tìm kiếm tương đồng ngữ nghĩa chỉ trong phạm vi của một mã dự án (project_code)."""
    return retrieve(settings, query=query, k=k, project_code=project_code)


def retrieve_by_project_with_scores(
    settings: Settings,
    project_code: str,
    query: str,
    k: int | None = None,
    score_threshold: float | None = None,
) -> list[tuple[Document, float]]:
    """Tìm kiếm tương đồng kèm điểm tương đồng chỉ trong phạm vi của một mã dự án (project_code)."""
    return retrieve_with_scores(
        settings,
        query=query,
        k=k,
        score_threshold=score_threshold,
        project_code=project_code,
    )


def list_projects(settings: Settings) -> list[str]:
    """Liệt kê danh sách tất cả các mã dự án (project_code) hiện có trong vector store."""
    store = _get_store(settings)
    try:
        res = store._collection.get(include=["metadatas"])
        found: set[str] = set()
        for m in res.get("metadatas", []):
            if m and "project_code" in m:
                found.add(str(m["project_code"]))
        return sorted(list(found))
    except Exception:
        return []


def get_project_documents(settings: Settings, project_code: str) -> list[Document]:
    """Lấy toàn bộ các đoạn văn bản thuộc về một mã dự án (không cần vector search)."""
    store = _get_store(settings)
    docs: list[Document] = []
    try:
        res = store._collection.get(
            where={"project_code": project_code},
            include=["documents", "metadatas"],
        )
        for d_id, text, meta in zip(
            res.get("ids", []), res.get("documents", []), res.get("metadatas", [])
        ):
            meta_copy = dict(meta or {})
            meta_copy["id"] = d_id
            docs.append(Document(page_content=text, metadata=meta_copy))
    except Exception:
        pass
    return docs


def delete_project_documents(settings: Settings, project_code: str) -> int:
    """Xóa toàn bộ vector và tài liệu thuộc mã dự án tương ứng. Trả về số chunk đã xóa."""
    store = _get_store(settings)
    try:
        existing = store._collection.get(where={"project_code": project_code})
        ids = existing.get("ids", [])
        if ids:
            store._collection.delete(ids=ids)
            return len(ids)
    except Exception:
        pass
    return 0



