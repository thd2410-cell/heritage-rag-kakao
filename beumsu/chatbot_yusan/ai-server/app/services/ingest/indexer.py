class Indexer:
    """Indexing boundary for PostgreSQL FTS/pgvector, OpenSearch, Qdrant, or Milvus."""

    def index(self, documents):
        return {"indexed": len(documents)}
