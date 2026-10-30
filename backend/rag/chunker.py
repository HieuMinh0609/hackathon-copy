"""Chia nhỏ tài liệu đa ngôn ngữ (VI/EN/KR) thành các chunk ngữ nghĩa tối ưu."""
from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config.settings import Settings

# Bộ phân tách câu đa ngôn ngữ ưu tiên toàn vẹn ngữ pháp câu cho Tiếng Việt, Tiếng Anh và Tiếng Hàn
MULTILINGUAL_SEPARATORS = [
    "\n\n",     # Đoạn văn bản
    ".\n",      # Kết thúc câu và xuống dòng
    ".\r\n",    # Kết thúc câu xuống dòng Windows
    "?\n",      # Kết thúc câu hỏi xuống dòng
    "!\n",      # Kết thúc câu cảm thán xuống dòng
    ". ",       # Kết thúc câu chuẩn
    "? ",       # Kết thúc câu hỏi
    "! ",       # Kết thúc câu cảm thán
    "\n",       # Xuống dòng đơn
    " ",        # Khoảng trắng giữa các từ
    "",         # Tách ký tự biên
]


def get_text_splitter(
    chunk_size: int = 1500,
    chunk_overlap: int = 150,
) -> RecursiveCharacterTextSplitter:
    """Tạo bộ cắt text tối ưu cho đa ngôn ngữ (tương đương ~700 tokens)."""
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=MULTILINGUAL_SEPARATORS,
        strip_whitespace=True,
    )


def split_documents(settings: Settings, docs: list[Document]) -> list[Document]:
    """Cắt danh sách tài liệu thành các chunk bảo toàn cấu trúc ngữ pháp ngoại ngữ."""
    # Chunk size từ settings (mặc định ~700 tokens ~ 1500 ký tự)
    chunk_size = getattr(settings, "chunk_size", 1500)
    chunk_overlap = getattr(settings, "chunk_overlap", 150)
    splitter = get_text_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return splitter.split_documents(docs)
