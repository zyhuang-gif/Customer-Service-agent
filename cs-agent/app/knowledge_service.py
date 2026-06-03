"""知识库文档管理：上传、列表、重建索引。"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

from app.config import settings
from app.retrieval.ingest import ingest

ALLOWED_SUFFIXES = {".md", ".txt"}


def _knowledge_dir() -> Path:
    path = Path(settings.knowledge_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_file_name(file_name: str) -> str:
    name = Path(file_name).name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="仅支持 Markdown(.md) 和 TXT(.txt) 文件")
    return re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", name)


def _document_info(path: Path) -> dict:
    stat = path.stat()
    return {
        "file_name": path.name,
        "file_type": path.suffix.lower().lstrip("."),
        "size": stat.st_size,
    }


def save_document(file_name: str, content: str) -> dict:
    file_name = _safe_file_name(file_name)
    if not content:
        raise HTTPException(status_code=400, detail="文件内容不能为空")
    target = _knowledge_dir() / file_name
    target.write_text(content, encoding="utf-8")
    return _document_info(target)


def list_documents() -> list[dict]:
    root = _knowledge_dir()
    docs = [
        _document_info(path)
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES
    ]
    return sorted(docs, key=lambda item: item["file_name"])


def reindex_documents() -> dict:
    chunks = ingest(force=True)
    return {"chunks": chunks}
