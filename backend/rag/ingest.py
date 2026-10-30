"""Pipeline nạp tài liệu đa ngôn ngữ (VI/EN/KR):
Load (PyMuPDF / python-docx / UTF-8) -> Chunk (Sentence Recursive) -> ThreadPool & Queue (Batch 32-64) -> Ollama (bge-m3) -> ChromaDB.
"""
from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from langchain_core.documents import Document

from config.settings import Settings
from backend.rag.chunker import split_documents
from backend.rag.loaders.docx_loader import load_docx
from backend.rag.loaders.pdf_loader import load_pdf

SUPPORTED = {".pdf", ".docx", ".md", ".txt"}


@dataclass
class IngestReport:
    files: int = 0
    chunks: int = 0
    batches: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        msg = f"Đã nạp {self.files} file, {self.chunks} chunk ({self.batches} lô)."
        return msg + (f" Lỗi ({len(self.errors)}): {'; '.join(self.errors[:3])}" if self.errors else "")


def discover_files(directory: Path) -> list[Path]:
    """Tìm tất cả các tệp tài liệu được hỗ trợ trong thư mục."""
    if not directory.exists():
        return []
    return sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)


def infer_role(path: Path, root: Path) -> str:
    """Thư mục con đầu tiên dưới documents/ chính là role (onboarding, hr, backend_developer...)."""
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError:
        return "onboarding"
    return parts[0] if len(parts) > 1 else "onboarding"


def load_file(path: Path) -> list[Document]:
    """Đọc tệp chuẩn UTF-8 đa ngôn ngữ, giữ nguyên vẹn font Tiếng Việt và Hangul (Hàn Quốc)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path)
    if suffix == ".docx":
        return load_docx(path)
    if suffix in {".md", ".txt"}:
        # Xử lý UTF-8 với khả năng nhận diện BOM (utf-8-sig)
        try:
            text = path.read_text(encoding="utf-8-sig").strip()
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        return (
            [
                Document(
                    page_content=text,
                    metadata={"source": path.name, "file_type": suffix.lstrip(".")},
                )
            ]
            if text
            else []
        )
    raise ValueError(f"Định dạng không hỗ trợ: {suffix}")


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Đảm bảo metadata chỉ chứa kiểu dữ liệu hợp lệ cho ChromaDB (str, int, float, bool)."""
    clean: dict[str, str | int | float | bool] = {}
    for k, v in metadata.items():
        if isinstance(v, (str, int, float, bool)):
            clean[k] = v
        elif v is not None:
            clean[k] = str(v)
    return clean


def _make_chunk_id(path: Path, index: int, content: str) -> str:
    """Tạo ID chunk duy nhất bằng hash SHA-256 để upsert không bị trùng lặp."""
    raw = f"{path.as_posix()}:{index}:{content[:64]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def ingest_files(
    settings: Settings,
    files: list[Path],
    root: Path | None = None,
    reset: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
    batch_size: int = 48,
    max_workers: int = 3,
    project_code: str | None = None,
) -> IngestReport:
    """Nạp danh sách tệp vào ChromaDB với xử lý đa luồng & chia lô an toàn.
    
    - project_code: Mã định danh dự án (nếu truyền, dữ liệu sẽ gắn cố định theo dự án này).
    - batch_size: 32 - 64 chunk/lô để tránh tràn VRAM của Ollama.
    - max_workers: 2 - 4 luồng gọi API sang Ollama embedding đồng thời.
    - An toàn luồng: Đồng bộ hóa ghi xuống ChromaDB (thread-safe batch upsert).
    - UI: Cập nhật tiến độ realtime qua callback progress(i, total, msg).
    """
    from backend.rag import vector_store

    root = root or settings.documents_dir
    report = IngestReport()

    store = vector_store.get_vector_store(settings)

    if reset:
        try:
            if project_code:
                # Chỉ xóa dữ liệu của riêng dự án này
                existing = store._collection.get(where={"project_code": project_code})
                if existing.get("ids"):
                    store._collection.delete(ids=existing["ids"])
            else:
                vector_store.reset_vector_store(settings)
                store = vector_store.get_vector_store(settings)
        except Exception as exc:
            report.errors.append(f"Reset vector store: {exc}")

    # 1. Tải và chia nhỏ tài liệu thành các chunk (UTF-8, câu hoàn chỉnh)
    all_chunks: list[Document] = []
    chunk_ids: list[str] = []

    for path in files:
        try:
            # Tài liệu trong folder riêng của project dùng project_code để cô lập;
            # gắn onboarding để mọi role của chính project đó đều truy xuất được.
            role = "onboarding" if project_code else infer_role(path, root)
            docs = load_file(path)
            for d in docs:
                d.metadata.update({"role": role, "path": str(path)})
                if project_code:
                    d.metadata["project_code"] = project_code
            
            chunks = split_documents(settings, docs)
            if not chunks:
                continue

            for idx, c in enumerate(chunks):
                if project_code:
                    c.metadata["project_code"] = project_code
                c.metadata = _sanitize_metadata(c.metadata)
                all_chunks.append(c)
                chunk_id_seed = f"{project_code}:{c.page_content}" if project_code else c.page_content
                chunk_ids.append(_make_chunk_id(path, idx, chunk_id_seed))

            report.files += 1
        except Exception as exc:
            report.errors.append(f"{path.name}: {exc}")

    total_chunks = len(all_chunks)
    report.chunks = total_chunks

    if total_chunks == 0:
        if progress:
            progress(1, 1, "Không có nội dung mới để nạp.")
        return report

    # 2. Chia lô an toàn (32 - 64 chunks/batch để tránh quá tải Ollama)
    safe_batch_size = max(16, min(64, batch_size))
    chunk_batches: list[list[Document]] = []
    id_batches: list[list[str]] = []

    for i in range(0, total_chunks, safe_batch_size):
        chunk_batches.append(all_chunks[i : i + safe_batch_size])
        id_batches.append(chunk_ids[i : i + safe_batch_size])

    total_batches = len(chunk_batches)
    report.batches = total_batches

    # 3. Đa luồng (ThreadPool) gọi embedding Ollama song song & ghi an toàn vào ChromaDB
    safe_workers = max(1, min(4, max_workers))
    db_lock = threading.Lock()
    processed_chunks = 0
    embedding_func = getattr(store, "embedding_function", None)

    def _process_one_batch(b_idx: int, b_docs: list[Document], b_ids: list[str]) -> int:
        texts = [d.page_content for d in b_docs]
        metas = [d.metadata for d in b_docs]

        # Bước 4: Gọi embedding Ollama (chạy song song ngoài lock, không nghẽn)
        vectors = None
        if embedding_func is not None and hasattr(embedding_func, "embed_documents"):
            try:
                vectors = embedding_func.embed_documents(texts)
            except Exception as emb_exc:
                raise RuntimeError(f"Lỗi embedding Ollama (lô {b_idx + 1}): {emb_exc}") from emb_exc

        # Bước 5: Ghi xuống ChromaDB (dưới lock để đảm bảo thread-safe đồng bộ hóa ổ đĩa)
        with db_lock:
            try:
                if vectors is not None and hasattr(store, "_collection"):
                    store._collection.upsert(
                        ids=b_ids,
                        embeddings=vectors,
                        metadatas=metas,
                        documents=texts,
                    )
                else:
                    store.add_documents(b_docs, ids=b_ids)
            except Exception as db_exc:
                raise RuntimeError(f"Lỗi ghi ChromaDB (lô {b_idx + 1}): {db_exc}") from db_exc

        return len(b_docs)

    # Khởi tạo tiến độ ban đầu
    if progress:
        progress(0, total_chunks, f"Bắt đầu nạp {total_chunks} chunks ({total_batches} lô)...")

    with ThreadPoolExecutor(max_workers=safe_workers) as executor:
        futures = {
            executor.submit(_process_one_batch, idx, b_docs, b_ids): idx
            for idx, (b_docs, b_ids) in enumerate(zip(chunk_batches, id_batches))
        }

        for future in as_completed(futures):
            b_idx = futures[future]
            try:
                count = future.result()
                processed_chunks += count
                pct = int((processed_chunks / total_chunks) * 100)
                if progress:
                    progress(
                        processed_chunks,
                        total_chunks,
                        f"Đã nạp {processed_chunks}/{total_chunks} chunks ({pct}%)",
                    )
            except Exception as batch_exc:
                report.errors.append(str(batch_exc))

    return report


def ingest_directory(
    settings: Settings,
    directory: Path | None = None,
    reset: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
    batch_size: int = 48,
    max_workers: int = 3,
    project_code: str | None = None,
) -> IngestReport:
    """Nạp toàn bộ tài liệu trong thư mục documents/ với xử lý đa luồng."""
    directory = directory or settings.documents_dir
    files = discover_files(directory)
    return ingest_files(
        settings,
        files,
        root=directory,
        reset=reset,
        progress=progress,
        batch_size=batch_size,
        max_workers=max_workers,
        project_code=project_code,
    )


def ingest_project_files(
    settings: Settings,
    project_code: str,
    files: list[Path],
    reset_project: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
    batch_size: int = 48,
    max_workers: int = 3,
) -> IngestReport:
    """Nạp danh sách nhiều tệp tài liệu (PDF, Word, TXT...) gắn liền với mã dự án (project_code).
    
    - Áp dụng đầy đủ: PyMuPDF/python-docx (UTF-8) -> Splitter (~700 tokens) -> ThreadPool 2-4 luồng / Batch 32-64 -> ChromaDB.
    - Tất cả các chunk được gán metadata 'project_code' để truy vấn cô lập hoàn toàn giữa các dự án.
    """
    return ingest_files(
        settings,
        files,
        reset=reset_project,
        progress=progress,
        batch_size=batch_size,
        max_workers=max_workers,
        project_code=project_code,
    )

