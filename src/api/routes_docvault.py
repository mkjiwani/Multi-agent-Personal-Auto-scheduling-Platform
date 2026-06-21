"""DocVault RAG API routes."""

from fastapi import APIRouter
from pydantic import BaseModel

from src.agents.docvault import docvault_agent

router = APIRouter(prefix="/api/docvault", tags=["docvault"])


class QueryRequest(BaseModel):
    question: str


class FolderRequest(BaseModel):
    folder_path: str


@router.get("/status")
async def get_status():
    """Get DocVault indexing status."""
    return docvault_agent.get_status()


@router.post("/query")
async def query_documents(req: QueryRequest):
    """Ask a question against the indexed documents."""
    result = await docvault_agent.query(req.question)
    return result


@router.post("/reindex")
async def reindex():
    """Re-scan and re-index all documents from all configured folders."""
    result = await docvault_agent.index_documents()
    return result


@router.post("/folders/add")
async def add_folder(req: FolderRequest):
    """Add a folder to the indexing list and trigger reindex."""
    return await docvault_agent.add_folder(req.folder_path)


@router.post("/folders/remove")
async def remove_folder(req: FolderRequest):
    """Remove a folder from the indexing list."""
    return docvault_agent.remove_folder(req.folder_path)
