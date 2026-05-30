from typing import Protocol

from app.schemas.retrieval import RetrievalRequest, RetrievalResult


class Retriever(Protocol):
    def retrieve(self, request: RetrievalRequest) -> list[RetrievalResult]:
        ...
