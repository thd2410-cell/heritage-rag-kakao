import hashlib
import math
from abc import ABC, abstractmethod

from app.core.config import settings


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class LocalMockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dims: int | None = None):
        self.dims = dims or settings.embedding_dimensions

    def embed(self, text: str) -> list[float]:
        dims = self.dims
        vector = [0.0] * dims
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode()).digest()
            idx = digest[0] % dims
            vector[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str, dimensions: int):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
        )
        return [list(item.embedding) for item in response.data]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class VectorScorer:
    def __init__(self, embedding_provider: EmbeddingProvider | None = None) -> None:
        self.embedding_provider = embedding_provider or build_embedding_provider()

    def score(self, query: str, content: str) -> float:
        return max(0.0, cosine(self.embedding_provider.embed(query), self.embedding_provider.embed(content)))


def build_embedding_provider() -> EmbeddingProvider:
    provider_name = (settings.embedding_provider or "mock").lower()
    if provider_name == "openai":
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    return LocalMockEmbeddingProvider(settings.embedding_dimensions)
