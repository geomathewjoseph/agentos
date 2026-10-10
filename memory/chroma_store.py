"""ChromaDB Vector Store — Persistent memory for AgentOS.

Stores and retrieves context using semantic similarity search.
Uses sentence-transformers for embeddings and ChromaDB for storage.
"""
from __future__ import annotations

import sys
import os
# Avoid Windows/Py313 torchvision C++ operator mismatch and suppress unused TF backends
os.environ["USE_TF"] = "0"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TRANSFORMERS_NO_TF"] = "1"
sys.modules["torchvision"] = None
sys.modules["torchvision.transforms"] = None

import uuid
import chromadb
from tools.logger import log

# Lazy-load sentence transformer to avoid slow import on startup
_embedder = None
_client   = None


def _get_client():
    """Get or create the ChromaDB persistent client."""
    global _client
    if _client is None:
        import os
        db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "agentos_memory"
        )
        _client = chromadb.PersistentClient(path=db_path)
    return _client


def _get_embedder():
    """Get or create the sentence transformer model."""
    global _embedder
    if _embedder is None:
        try:
            import sys
            # Avoid Windows/Py313 torchvision C++ operator mismatch in transformers
            sys.modules["torchvision"] = None
            sys.modules["torchvision.transforms"] = None
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer("all-MiniLM-L6-v2")
            log("chroma", "Loaded embedding model: all-MiniLM-L6-v2", "success")
        except Exception as e:
            log("chroma", f"Failed to load embedding model: {e}", "error")
            raise
    return _embedder


def _col(name: str):
    """Get or create a ChromaDB collection."""
    return _get_client().get_or_create_collection(name)


def store(collection: str, text: str, meta: dict | None = None):
    """Store a document in a ChromaDB collection.
    
    Args:
        collection: Collection name (e.g., 'planning', 'coding')
        text: Document text to store
        meta: Optional metadata dict
    """
    if meta is None:
        meta = {}
    try:
        emb = _get_embedder().encode(text).tolist()
        _col(collection).add(
            documents=[text],
            embeddings=[emb],
            metadatas=[meta],
            ids=[str(uuid.uuid4())],
        )
    except Exception as e:
        log("chroma", f"Failed to store document: {e}", "warning")


def query(collection: str, text: str, n: int = 3) -> list[str]:
    """Query a collection for similar documents.
    
    Args:
        collection: Collection name
        text: Query text
        n: Number of results to return
    
    Returns:
        List of matching document strings
    """
    try:
        emb = _get_embedder().encode(text).tolist()
        res = _col(collection).query(query_embeddings=[emb], n_results=n)
        return res["documents"][0] if res["documents"] else []
    except Exception as e:
        log("chroma", f"Query failed: {e}", "warning")
        return []
