"""
RAG module — iStatis catalog indexer and retriever.

Embeds backend/data/istatis_catalog.json into a local Chroma vector store
(chroma_istatis/) using OpenAI text-embedding-3-small.

Usage
-----
# Index once (creates / updates chroma_istatis/):
    cd C:\\Usama\\Projects\\istatis-papers
    venv\\Scripts\\python backend/rag.py

# Import in any agent:
    from backend.rag import query_catalog
    context = query_catalog("C4 envelope pricing")
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent                          # backend/
CATALOG_PATH = _HERE / "data" / "istatis_catalog.json"
CHROMA_DIR = _HERE.parent / "chroma_istatis"              # project root / chroma_istatis
COLLECTION_NAME = "istatis_catalog"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_catalog() -> list[Document]:
    """Read istatis_catalog.json and convert each entry to a LangChain Document."""
    with open(CATALOG_PATH, "r", encoding="utf-8") as fh:
        entries = json.load(fh)

    docs: list[Document] = []
    for entry in entries:
        # page_content = title + full content for richer embedding
        page_content = f"{entry['title']}\n\n{entry['content']}"
        metadata = {k: v for k, v in entry.items() if k != "content"}
        docs.append(Document(page_content=page_content, metadata=metadata))
    return docs


def _get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model="text-embedding-3-small")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def index_catalog() -> int:
    """
    Embed all catalog documents and persist them in chroma_istatis/.

    Safe to call repeatedly — Chroma will overwrite the collection.
    Returns the number of documents indexed.
    """
    docs = _load_catalog()

    # Delete existing collection first so we don't accumulate duplicates
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"  Deleted existing '{COLLECTION_NAME}' collection.")
    except Exception:
        pass  # collection didn't exist yet

    Chroma.from_documents(
        documents=docs,
        embedding=_get_embeddings(),
        collection_name=COLLECTION_NAME,
        persist_directory=str(CHROMA_DIR),
    )
    return len(docs)


def get_vectorstore() -> Chroma:
    """Return a Chroma instance pointing at the persisted catalog collection."""
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=_get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )


def query_catalog(question: str, k: int = 3) -> str:
    """
    Semantic search over the iStatis catalog.

    Returns a formatted string with the top-k matching catalog entries.
    Raises RuntimeError if the collection hasn't been indexed yet.
    """
    vs = get_vectorstore()
    results = vs.similarity_search(question, k=k)

    if not results:
        return "No relevant catalog entries found."

    parts: list[str] = []
    for i, doc in enumerate(results, 1):
        cat = doc.metadata.get("category", "")
        header = f"[{i}] {doc.metadata.get('title', '')} ({cat})"
        parts.append(f"{header}\n{doc.page_content.split(chr(10), 2)[-1]}")

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# CLI: run directly to index the catalog
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("iStatis — Catalog Indexer")
    print("=" * 60)
    print(f"  Catalog : {CATALOG_PATH}")
    print(f"  Store   : {CHROMA_DIR}")
    print()

    print("Indexing catalog documents...")
    n = index_catalog()
    print(f"[OK] Indexed {n} documents.\n")

    # Quick smoke test
    test_queries = [
        "C4 envelope pricing for 1000 units",
        "A4 paper 80gsm bulk price",
        "custom logo printing on envelopes",
    ]
    print("Smoke tests:")
    for q in test_queries:
        print(f"\n  Query: {q!r}")
        result = query_catalog(q, k=1)
        first_line = result.splitlines()[0] if result else "(empty)"
        print(f"  -> {first_line}")

    print("\n[OK] RAG ready. Import query_catalog() in your agents.")
    print("=" * 60)
