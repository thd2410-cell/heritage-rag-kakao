from abc import ABC, abstractmethod

from app.schemas.retrieval import RetrievalResult


SOURCE_ORDER = {"official_db": 4, "signboard": 3, "glossary": 2, "report": 1}


class CrossEncoderReranker(ABC):
    @abstractmethod
    def rerank(self, query: str, results: list[RetrievalResult], selected_entity_ids: list[str]) -> list[RetrievalResult]:
        raise NotImplementedError


class MockReranker(CrossEncoderReranker):
    def rerank(self, query: str, results: list[RetrievalResult], selected_entity_ids: list[str]) -> list[RetrievalResult]:
        seen = set()
        filtered = []
        for result in results:
            if len(result.content.strip()) < 10 or result.content in seen:
                continue
            seen.add(result.content)
            selected_bonus = 0.1 if result.heritage_id in selected_entity_ids else 0.0
            source_bonus = SOURCE_ORDER.get(result.source_type, 0) / 100
            result.score = round(result.score + selected_bonus + source_bonus, 4)
            filtered.append(result)
        return sorted(filtered, key=lambda item: item.score, reverse=True)
