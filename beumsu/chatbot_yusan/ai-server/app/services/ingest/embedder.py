from app.services.retrieval.vector_retriever import LocalMockEmbeddingProvider


class Embedder:
    def __init__(self):
        self.provider = LocalMockEmbeddingProvider()

    def embed(self, text: str) -> list[float]:
        return self.provider.embed(text)
