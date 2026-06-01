from app.retrieval.chunking import chunk_markdown


def test_chunk_by_h2_headings():
    md = "# 标题\n\n## A 政策\n内容A1\n内容A2\n\n## B 政策\n内容B1\n"
    chunks = chunk_markdown(md, source="x.md")
    assert len(chunks) == 2
    assert chunks[0]["title"] == "A 政策"
    assert "内容A1" in chunks[0]["text"]
    assert "内容A2" in chunks[0]["text"]
    assert chunks[0]["source"] == "x.md"
    assert chunks[1]["title"] == "B 政策"


def test_chunk_skips_empty_sections():
    md = "# 大标题\n\n## 只有标题没内容\n\n## 有内容\n正文\n"
    chunks = chunk_markdown(md, source="x.md")
    titles = [c["title"] for c in chunks]
    assert "有内容" in titles
    assert "只有标题没内容" not in titles
