"""Đọc file PDF chuẩn UTF-8 bằng PyMuPDF, bảo toàn nguyên vẹn font Tiếng Việt và Hangul (Hàn Quốc)."""
from __future__ import annotations

from pathlib import Path
from langchain_core.documents import Document


def load_pdf(path: Path) -> list[Document]:
    """Trích xuất nội dung từ PDF thành danh sách Document theo từng trang."""
    docs: list[Document] = []
    
    # Ưu tiên PyMuPDF (nhanh, chuẩn UTF-8, giữ trọn vẹn dấu tiếng Việt và chữ Hangul)
    try:
        import pymupdf
        with pymupdf.open(str(path)) as pdf_doc:
            for page_no, page in enumerate(pdf_doc, start=1):
                text = (page.get_text("text") or "").strip()
                if text:
                    docs.append(
                        Document(
                            page_content=text,
                            metadata={"source": path.name, "page": page_no, "file_type": "pdf"},
                        )
                    )
        if docs:
            return docs
    except Exception:
        # Fallback sang pypdf nếu PyMuPDF gặp lỗi đặc thù
        pass

    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        for page_no, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                docs.append(
                    Document(
                        page_content=text,
                        metadata={"source": path.name, "page": page_no, "file_type": "pdf"},
                    )
                )
    except Exception as exc:
        raise RuntimeError(f"Không thể đọc file PDF '{path.name}': {exc}") from exc

    return docs
