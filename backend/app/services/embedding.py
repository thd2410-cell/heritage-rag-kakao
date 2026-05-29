from functools import lru_cache
from app.core.config import get_settings


@lru_cache
def get_embedding_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Install backend/requirements.ml.txt for embedding/RAG ingestion."
        ) from exc
    return SentenceTransformer(get_settings().embedding_model)


def embed_text(text: str) -> list[float]:
    model = get_embedding_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.astype(float).tolist()
