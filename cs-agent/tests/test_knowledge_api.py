def test_upload_markdown_document_lists_file_and_reindexes(client, monkeypatch, tmp_path):
    import app.knowledge_service as knowledge_service
    import app.retrieval.ingest as ingest_module

    monkeypatch.setattr(knowledge_service.settings, "knowledge_dir", str(tmp_path))
    monkeypatch.setattr(ingest_module.settings, "knowledge_dir", str(tmp_path))
    monkeypatch.setattr(ingest_module, "build_store", lambda: FakeStore())

    upload = client.post(
        "/knowledge/documents",
        json={"file_name": "refund_policy.md", "content": "# Refund\n\n## Time\n1-5 days"},
    )
    assert upload.status_code == 200
    assert upload.json()["file_name"] == "refund_policy.md"

    listed = client.get("/knowledge/documents")
    assert listed.status_code == 200
    assert listed.json()[0]["file_name"] == "refund_policy.md"

    reindexed = client.post("/knowledge/reindex")
    assert reindexed.status_code == 200
    assert reindexed.json()["chunks"] == 1


def test_upload_rejects_unsupported_file_type(client, monkeypatch, tmp_path):
    import app.knowledge_service as knowledge_service

    monkeypatch.setattr(knowledge_service.settings, "knowledge_dir", str(tmp_path))

    r = client.post(
        "/knowledge/documents",
        json={"file_name": "policy.pdf", "content": "%PDF"},
    )

    assert r.status_code == 400
    assert "仅支持" in r.json()["detail"]


class FakeStore:
    def __init__(self):
        self.reset_called = False

    def count(self):
        return 0

    def reset(self):
        self.reset_called = True

    def add_chunks(self, chunks):
        self.chunks = chunks
