"""按 Markdown 二级标题(## )切块。每块带 title/source/text。"""
from __future__ import annotations


def chunk_markdown(md: str, source: str) -> list[dict]:
    chunks: list[dict] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush():
        if current_title is not None:
            text = "\n".join(current_lines).strip()
            if text:
                chunks.append({"title": current_title, "source": source, "text": text})

    for line in md.splitlines():
        if line.startswith("## "):
            flush()
            current_title = line[3:].strip()
            current_lines = []
        elif line.startswith("# "):
            continue
        else:
            if current_title is not None:
                current_lines.append(line)
    flush()
    return chunks
