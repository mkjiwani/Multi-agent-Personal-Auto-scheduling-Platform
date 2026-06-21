"""Agent-5: DocVault — Local RAG (Retrieval-Augmented Generation) agent.

Indexes documents from a configurable folder, chunks them, and uses
TF-IDF retrieval + LLM generation for question answering.

Index is persisted to disk so it survives restarts without full re-read.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from src.agents.base_agent import BaseAgent
from src.config import settings, BASE_DIR
from src.llm.ollama_client import ollama_client

logger = logging.getLogger(__name__)

# Persistence paths
CACHE_DIR = BASE_DIR / "data" / "docvault_cache"
INDEX_FILE = CACHE_DIR / "tfidf_index.joblib"
CHUNKS_FILE = CACHE_DIR / "chunks.joblib"
MANIFEST_FILE = CACHE_DIR / "manifest.json"

RAG_PROMPT = """You are a helpful assistant answering questions based on the provided document context.
Use ONLY the information from the context below to answer the question. If the answer is not in the context, say "I couldn't find that information in the indexed documents."

Context:
{context}

Question: {question}

Answer:"""

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


class DocVaultAgent(BaseAgent):
    """Indexes local documents and answers questions using RAG."""

    def __init__(self):
        super().__init__("docvault")
        self.documents: list[dict] = []  # {path, content, chunks}
        self.chunks: list[dict] = []  # {text, source, chunk_id}
        self.vectorizer: TfidfVectorizer | None = None
        self.tfidf_matrix = None
        self._indexed_at: datetime | None = None
        self._query_history: list[dict] = []
        # Multi-folder support: list of folder paths
        self._folders: list[Path] = []
        initial = settings.rag_folder_path.strip()
        if initial and initial != "./documents":
            self._folders.append(Path(initial))
        # File manifest: {relative_path: {mtime, size}} for change detection
        self._file_manifest: dict[str, dict] = {}
        # Try to load cached index from disk
        self._load_cache()

    async def run(self):
        """Main loop — re-index periodically."""
        await self.run_loop(interval_seconds=3600, initial_delay=30)

    async def execute(self):
        """Index documents from all configured folders."""
        self.logger.info(f"Indexing documents from {len(self._folders)} folders")
        await self.index_documents()

    async def add_folder(self, folder_path: str, auto_reindex: bool = True) -> dict:
        """Add a folder to the index list and optionally trigger reindex."""
        p = Path(folder_path)
        if not p.exists():
            return {"error": f"Folder does not exist: {folder_path}"}
        if not p.is_dir():
            return {"error": f"Path is not a directory: {folder_path}"}
        if p in self._folders:
            return {"error": "Folder already added"}
        self._folders.append(p)
        result = {"added": str(p), "folders": [str(f) for f in self._folders]}
        if auto_reindex:
            index_result = await self.index_documents()
            result.update(index_result)
        return result

    def remove_folder(self, folder_path: str) -> dict:
        """Remove a folder from the index list."""
        p = Path(folder_path)
        if p in self._folders:
            self._folders.remove(p)
            return {"removed": str(p), "folders": [str(f) for f in self._folders]}
        return {"error": "Folder not found in list"}

    async def index_documents(self) -> dict:
        """Scan all folders, read documents, chunk and build TF-IDF index.

        Uses file manifest to detect changes — only re-reads modified/new files.
        Persists the index to disk after building.
        """
        import asyncio

        if not self._folders:
            self.logger.warning("No folders configured for indexing")
            return self.get_status()

        # Build current file manifest from filesystem
        current_files: dict[str, dict] = {}  # key: "folder|relpath"
        all_file_paths: dict[str, Path] = {}  # same key -> absolute Path

        for folder in self._folders:
            if not folder.exists():
                self.logger.warning(f"Folder not found, skipping: {folder}")
                continue
            for ext in SUPPORTED_EXTENSIONS:
                for file_path in folder.rglob(f"*{ext}"):
                    if file_path.name.startswith("~$"):
                        continue
                    try:
                        stat = file_path.stat()
                        rel = str(file_path.relative_to(folder))
                        key = f"{folder}|{rel}"
                        current_files[key] = {
                            "mtime": stat.st_mtime,
                            "size": stat.st_size,
                        }
                        all_file_paths[key] = file_path
                    except OSError:
                        continue

        # Determine what changed since last index
        old_manifest = self._file_manifest
        new_keys = set(current_files.keys())
        old_keys = set(old_manifest.keys())

        added = new_keys - old_keys
        removed = old_keys - new_keys
        modified = {
            k for k in new_keys & old_keys
            if current_files[k]["mtime"] != old_manifest[k]["mtime"]
            or current_files[k]["size"] != old_manifest[k]["size"]
        }

        changed_keys = added | modified

        # If nothing changed and we have a valid index, skip
        if not changed_keys and not removed and self.tfidf_matrix is not None:
            self.logger.info("No file changes detected, index is current")
            return self.get_status()

        # If only some files changed and we have existing chunks, do incremental
        if self.chunks and (len(changed_keys) + len(removed)) < len(current_files) * 0.5:
            self.logger.info(
                f"Incremental reindex: {len(added)} added, {len(modified)} modified, {len(removed)} removed"
            )
            # Remove chunks from deleted/modified files
            keys_to_remove = removed | modified
            sources_to_remove = set()
            for k in keys_to_remove:
                parts = k.split("|", 1)
                if len(parts) == 2:
                    sources_to_remove.add(parts[1])

            self.chunks = [c for c in self.chunks if c["source"] not in sources_to_remove]
            self.documents = [d for d in self.documents if d["path"] not in sources_to_remove]

            # Read new/modified files
            total_changed = len(changed_keys)
            for idx, key in enumerate(changed_keys, 1):
                file_path = all_file_paths[key]
                parts = key.split("|", 1)
                folder_str, rel_path = parts[0], parts[1]
                if idx % 25 == 0 or idx == total_changed:
                    self.logger.info(f"Reindex progress: {idx}/{total_changed} files processed")
                try:
                    content = await asyncio.to_thread(self._read_file, file_path)
                    if content.strip():
                        doc = {
                            "path": rel_path,
                            "folder": folder_str,
                            "content": content,
                            "size": len(content),
                        }
                        self.documents.append(doc)
                        doc_chunks = self._chunk_text(
                            content,
                            chunk_size=settings.rag_chunk_size,
                            overlap=settings.rag_chunk_overlap,
                        )
                        for i, chunk_text in enumerate(doc_chunks):
                            self.chunks.append({
                                "text": chunk_text,
                                "source": rel_path,
                                "chunk_id": f"{rel_path}#{i}",
                            })
                except Exception as e:
                    self.logger.warning(f"Failed to read {file_path}: {e}")
        else:
            # Full reindex
            total_files = len(all_file_paths)
            self.logger.info(f"Full reindex starting — {total_files} files to process...")
            documents = []
            for idx, (key, file_path) in enumerate(all_file_paths.items(), 1):
                parts = key.split("|", 1)
                folder_str, rel_path = parts[0], parts[1]
                if idx % 50 == 0 or idx == total_files:
                    pct = int(idx / total_files * 100)
                    self.logger.info(f"Reindex progress: {idx}/{total_files} files ({pct}%)")
                try:
                    content = await asyncio.to_thread(self._read_file, file_path)
                    if content.strip():
                        documents.append({
                            "path": rel_path,
                            "folder": folder_str,
                            "content": content,
                            "size": len(content),
                        })
                except Exception as e:
                    self.logger.warning(f"Failed to read {file_path}: {e}")

            self.documents = documents
            self.logger.info(f"Read {len(documents)} documents")

            # Chunk documents
            self.chunks = []
            for doc in documents:
                doc_chunks = self._chunk_text(
                    doc["content"],
                    chunk_size=settings.rag_chunk_size,
                    overlap=settings.rag_chunk_overlap,
                )
                for i, chunk_text in enumerate(doc_chunks):
                    self.chunks.append({
                        "text": chunk_text,
                        "source": doc["path"],
                        "chunk_id": f"{doc['path']}#{i}",
                    })

            self.logger.info(f"Created {len(self.chunks)} chunks")

        # Rebuild TF-IDF index
        if self.chunks:
            texts = [c["text"] for c in self.chunks]
            self.vectorizer = TfidfVectorizer(
                stop_words="english",
                max_features=10000,
                ngram_range=(1, 2),
            )
            self.tfidf_matrix = self.vectorizer.fit_transform(texts)
            self.logger.info("TF-IDF index built successfully")
        else:
            self.vectorizer = None
            self.tfidf_matrix = None

        # Update manifest and persist
        self._file_manifest = current_files
        self._indexed_at = datetime.utcnow()
        self._save_cache()
        return self.get_status()

    async def query(self, question: str) -> dict:
        """Answer a question using RAG retrieval + LLM generation."""
        if not self.chunks or self.vectorizer is None:
            return {
                "answer": "No documents indexed yet. Please add files to the RAG folder and click 'Re-index'.",
                "sources": [],
                "question": question,
            }

        # Retrieve relevant chunks
        retrieved = self._retrieve(question, top_k=settings.rag_top_k)

        # Build context from retrieved chunks
        context = "\n\n---\n\n".join(
            f"[Source: {r['source']}]\n{r['text']}" for r in retrieved
        )

        # Generate answer with LLM
        try:
            prompt = RAG_PROMPT.format(context=context, question=question)
            answer = await ollama_client.generate(
                prompt=prompt,
                agent_name="docvault",
                temperature=0.3,
                think=False,
            )
            answer = answer.strip()
        except Exception as e:
            self.logger.error(f"LLM generation error: {e}")
            answer = "Sorry, the LLM is currently busy. Please try again in a moment."

        result = {
            "answer": answer,
            "sources": [{"source": r["source"], "relevance": r["score"]} for r in retrieved],
            "question": question,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Store in history
        self._query_history.insert(0, result)
        self._query_history = self._query_history[:50]

        return result

    def _retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve top-k relevant chunks using TF-IDF cosine similarity."""
        query_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0.01:  # Minimum relevance threshold
                results.append({
                    "text": self.chunks[idx]["text"],
                    "source": self.chunks[idx]["source"],
                    "chunk_id": self.chunks[idx]["chunk_id"],
                    "score": round(float(scores[idx]), 4),
                })

        return results

    def get_status(self) -> dict:
        """Get agent status for dashboard."""
        return {
            "indexed_documents": len(self.documents),
            "total_chunks": len(self.chunks),
            "indexed_at": self._indexed_at.isoformat() if self._indexed_at else None,
            "folders": [str(f) for f in self._folders],
            "query_history": self._query_history[:10],
        }

    def _save_cache(self):
        """Persist TF-IDF index, chunks, and manifest to disk."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)

            # Save vectorizer + tfidf matrix
            joblib.dump(
                {"vectorizer": self.vectorizer, "tfidf_matrix": self.tfidf_matrix},
                INDEX_FILE,
            )

            # Save chunks (without storing full document content — just metadata)
            joblib.dump(self.chunks, CHUNKS_FILE)

            # Save manifest + metadata as JSON
            manifest_data = {
                "file_manifest": self._file_manifest,
                "indexed_at": self._indexed_at.isoformat() if self._indexed_at else None,
                "num_documents": len(self.documents),
                "num_chunks": len(self.chunks),
                "folders": [str(f) for f in self._folders],
                "chunk_size": settings.rag_chunk_size,
                "chunk_overlap": settings.rag_chunk_overlap,
            }
            MANIFEST_FILE.write_text(json.dumps(manifest_data), encoding="utf-8")

            self.logger.info(
                f"Index cache saved: {len(self.chunks)} chunks, {len(self.documents)} docs"
            )
        except Exception as e:
            self.logger.warning(f"Failed to save index cache: {e}")

    def _load_cache(self):
        """Load persisted index from disk if it exists and config matches."""
        try:
            if not INDEX_FILE.exists() or not CHUNKS_FILE.exists() or not MANIFEST_FILE.exists():
                self.logger.info("No index cache found, will build from scratch")
                return

            # Load manifest to validate
            manifest_data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))

            # Verify chunk settings match (if settings changed, must rebuild)
            if (
                manifest_data.get("chunk_size") != settings.rag_chunk_size
                or manifest_data.get("chunk_overlap") != settings.rag_chunk_overlap
            ):
                self.logger.info("Chunk settings changed, cache invalidated")
                return

            # Load index
            index_data = joblib.load(INDEX_FILE)
            self.vectorizer = index_data["vectorizer"]
            self.tfidf_matrix = index_data["tfidf_matrix"]

            # Load chunks
            self.chunks = joblib.load(CHUNKS_FILE)

            # Restore manifest
            self._file_manifest = manifest_data.get("file_manifest", {})
            indexed_at_str = manifest_data.get("indexed_at")
            if indexed_at_str:
                self._indexed_at = datetime.fromisoformat(indexed_at_str)

            # Restore folders from manifest (preserves user-added folders across restarts)
            saved_folders = manifest_data.get("folders", [])
            for f in saved_folders:
                p = Path(f)
                if p not in self._folders and p.exists():
                    self._folders.append(p)

            # Rebuild minimal documents list (without content, just metadata)
            self.documents = [
                {"path": key.split("|", 1)[1], "folder": key.split("|", 1)[0], "content": "", "size": 0}
                for key in self._file_manifest
            ]

            self.logger.info(
                f"Index cache loaded: {len(self.chunks)} chunks, {len(self.documents)} docs "
                f"(indexed at {indexed_at_str})"
            )
        except Exception as e:
            self.logger.warning(f"Failed to load index cache, will rebuild: {e}")
            # Reset to empty state
            self.chunks = []
            self.documents = []
            self.vectorizer = None
            self.tfidf_matrix = None
            self._file_manifest = {}

    def _read_file(self, file_path: Path) -> str:
        """Read file content based on extension."""
        ext = file_path.suffix.lower()

        if ext == ".txt" or ext == ".md":
            return file_path.read_text(encoding="utf-8", errors="ignore")

        elif ext == ".pdf":
            return self._read_pdf(file_path)

        elif ext == ".docx":
            return self._read_docx(file_path)

        return ""

    def _read_pdf(self, file_path: Path) -> str:
        """Extract text from PDF."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
        except Exception as e:
            self.logger.warning(f"PDF read error {file_path}: {e}")
            return ""

    def _read_docx(self, file_path: Path) -> str:
        """Extract text from Word document, tolerating corrupted media files."""
        # First try normal python-docx
        try:
            from docx import Document
            doc = Document(str(file_path))
            text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())
            if text:
                return text
        except Exception as e:
            err = str(e)
            # If it's a CRC/corruption error, try XML fallback
            if "CRC" in err or "Checksum" in err or "BadZip" in err or "Package not found" in err:
                return self._read_docx_fallback(file_path)
            self.logger.warning(f"DOCX read error {file_path}: {e}")
            return ""
        return ""

    def _read_docx_fallback(self, file_path: Path) -> str:
        """Fallback: extract text from docx by parsing word/document.xml directly,
        bypassing CRC validation entirely for corrupted files."""
        import zipfile
        import re

        # Temporarily disable CRC checking in zipfile
        orig_update_crc = zipfile.ZipExtFile._update_crc
        zipfile.ZipExtFile._update_crc = lambda self, data: None
        try:
            with zipfile.ZipFile(str(file_path), "r") as zf:
                if "word/document.xml" not in zf.namelist():
                    return ""
                xml_content = zf.read("word/document.xml").decode("utf-8", errors="ignore")
            # Strip XML tags to get plain text, preserve paragraph breaks
            xml_content = xml_content.replace("</w:p>", "\n")
            text = re.sub(r"<[^>]+>", "", xml_content)
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            return "\n".join(lines)
        except Exception as e:
            self.logger.warning(f"DOCX fallback failed {file_path.name}: {e}")
            return ""
        finally:
            zipfile.ZipExtFile._update_crc = orig_update_crc

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks."""
        if len(text) <= chunk_size:
            return [text] if text.strip() else []

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size

            # Try to break at a sentence boundary
            if end < len(text):
                # Look for sentence end near the chunk boundary
                for sep in [". ", ".\n", "\n\n", "\n", " "]:
                    break_point = text.rfind(sep, start + chunk_size // 2, end + 50)
                    if break_point != -1:
                        end = break_point + len(sep)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - overlap

        return chunks


# Singleton instance
docvault_agent = DocVaultAgent()


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(docvault_agent.start())
