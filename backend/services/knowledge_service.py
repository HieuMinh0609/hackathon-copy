"""Dịch vụ tri thức: tìm kiếm RAG đa ngôn ngữ + nạp tài liệu với ThreadPool & Batching."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from langchain_core.documents import Document

from config.settings import Settings
from backend.rag import ingest, retriever


class KnowledgeService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(self, query: str, k: int | None = None) -> list[Document]:
        """Tìm kiếm ngữ nghĩa đa ngôn ngữ (VI/EN/KR) từ ChromaDB."""
        return retriever.retrieve(self.settings, query, k=k)

    def search_with_scores(
        self,
        query: str,
        k: int | None = None,
        score_threshold: float | None = None,
    ) -> list[tuple[Document, float]]:
        """Tìm kiếm ngữ nghĩa kèm điểm tương đồng/độ liên quan."""
        return retriever.retrieve_with_scores(
            self.settings, query, k=k, score_threshold=score_threshold
        )

    def ingest_all(
        self,
        reset: bool = False,
        progress: Callable[[int, int, str], None] | None = None,
        batch_size: int = 48,
        max_workers: int = 3,
        project_code: str | None = None,
    ) -> ingest.IngestReport:
        """Nạp toàn bộ tài liệu trong thư mục documents/ bằng ThreadPool (tùy chọn theo project_code)."""
        return ingest.ingest_directory(
            self.settings,
            reset=reset,
            progress=progress,
            batch_size=batch_size,
            max_workers=max_workers,
            project_code=project_code,
        )

    def ingest_paths(
        self,
        paths: list[Path],
        reset: bool = False,
        progress: Callable[[int, int, str], None] | None = None,
        batch_size: int = 48,
        max_workers: int = 3,
        project_code: str | None = None,
    ) -> ingest.IngestReport:
        """Nạp danh sách tệp tài liệu cụ thể bằng ThreadPool."""
        return ingest.ingest_files(
            self.settings,
            paths,
            reset=reset,
            progress=progress,
            batch_size=batch_size,
            max_workers=max_workers,
            project_code=project_code,
        )

    # ---- Thao tác nạp và truy xuất dữ liệu theo Mã Dự Án (Project Code) ----
    def ingest_project(
        self,
        project_code: str,
        files: list[Path],
        reset: bool = False,
        progress: Callable[[int, int, str], None] | None = None,
        batch_size: int = 48,
        max_workers: int = 3,
    ) -> ingest.IngestReport:
        """Nạp nhiều file tài liệu (PDF, Word, TXT...) gắn liền với mã dự án (project_code)."""
        return ingest.ingest_project_files(
            self.settings,
            project_code=project_code,
            files=files,
            reset_project=reset,
            progress=progress,
            batch_size=batch_size,
            max_workers=max_workers,
        )

    def search_project(
        self,
        project_code: str,
        query: str,
        k: int | None = None,
    ) -> list[Document]:
        """Truy xuất tài liệu tương đồng ngữ nghĩa trong phạm vi một mã dự án (project_code)."""
        return retriever.retrieve_by_project(
            self.settings, project_code=project_code, query=query, k=k
        )

    def search_project_with_scores(
        self,
        project_code: str,
        query: str,
        k: int | None = None,
        score_threshold: float | None = None,
    ) -> list[tuple[Document, float]]:
        """Tìm kiếm ngữ nghĩa kèm điểm tương đồng trong phạm vi một mã dự án (project_code)."""
        return retriever.retrieve_by_project_with_scores(
            self.settings,
            project_code=project_code,
            query=query,
            k=k,
            score_threshold=score_threshold,
        )

    def get_project_docs(self, project_code: str) -> list[Document]:
        """Lấy toàn bộ các đoạn tài liệu thuộc về một mã dự án."""
        return retriever.get_project_documents(self.settings, project_code=project_code)

    def delete_project_docs(self, project_code: str) -> int:
        """Xóa toàn bộ vector và tài liệu của một mã dự án."""
        return retriever.delete_project_documents(self.settings, project_code=project_code)

    def list_projects(self) -> list[str]:
        """Liệt kê danh sách tất cả các mã dự án hiện có trong vector store."""
        return retriever.list_projects(self.settings)

    def chunk_count(self) -> int:
        """Đếm tổng số chunk hiện có trong ChromaDB."""
        from backend.rag.vector_store import count_chunks

        return count_chunks(self.settings)

    @staticmethod
    def format_context(docs: Sequence[Document | tuple[Document, float]]) -> str:
        """Định dạng context đa ngôn ngữ phục vụ suy luận chéo cho LLM."""
        return retriever.format_multilingual_context(docs)

    @staticmethod
    def source_label(doc: Document) -> str:
        label = doc.metadata.get("source", "không rõ")
        if doc.metadata.get("page"):
            label += f", trang {doc.metadata['page']}"
        return label

    def sources(self, docs: list[Document]) -> list[str]:
        out: list[str] = []
        for d in docs:
            label = self.source_label(d)
            if label not in out:
                out.append(label)
        return out
