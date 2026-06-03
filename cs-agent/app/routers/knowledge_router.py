from fastapi import APIRouter
from pydantic import BaseModel

from app.knowledge_service import list_documents, reindex_documents, save_document

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeDocumentIn(BaseModel):
    file_name: str
    content: str


@router.post("/documents")
def upload_document(body: KnowledgeDocumentIn):
    return save_document(body.file_name, body.content)


@router.get("/documents")
def get_documents():
    return list_documents()


@router.post("/reindex")
def reindex_knowledge():
    return reindex_documents()
