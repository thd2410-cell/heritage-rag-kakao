from app.db.repository import HeritageRepository
from app.schemas.retrieval import RetrievalRequest, RetrievalResult
from app.core.config import settings
from app.services.cache.memory_cache import cache
from app.services.retrieval.graph_retriever import GraphRetriever
from app.services.retrieval.keyword_retriever import KeywordScorer
from app.services.retrieval.vector_retriever import VectorScorer


TRUST_BONUS = {"S1": 1.0, "S2": 0.7, "S3": 0.3, "S4": -1.0}


class HybridRetriever:
    def __init__(self, repo: HeritageRepository):
        self.repo = repo
        self.keyword = KeywordScorer()
        self.vector = VectorScorer()
        self.graph = GraphRetriever(repo)

    def retrieve(self, request: RetrievalRequest) -> list[RetrievalResult]:
        entity_ids = [e.heritage_id for e in request.normalized_entities]
        cache_key = f"retrieval:{request.query}:{','.join(entity_ids)}:{request.language}:{request.top_k}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        related = self.graph.expand(entity_ids) if entity_ids else {}
        search_entity_ids = list(dict.fromkeys(entity_ids + list(related.keys()))) or None
        terms = [request.query] + [e.official_name_ko for e in request.normalized_entities]
        postgres_results = self._retrieve_with_postgres_vector(
            request=request,
            terms=terms,
            entity_ids=entity_ids,
            related=related,
            search_entity_ids=search_entity_ids,
        )
        if postgres_results:
            cache.set(cache_key, postgres_results)
            return postgres_results

        chunks = self.repo.search_chunks(search_entity_ids)
        results = []
        for chunk, doc in chunks:
            if doc.source_trust_level == "S4":
                continue
            keyword_score = self.keyword.score(terms, doc.title, chunk.content)
            vector_score = self.vector.score(request.query, chunk.content)
            entity_bonus = 1.0 if chunk.heritage_entity_id in entity_ids else 0.0
            relation_bonus = related.get(chunk.heritage_entity_id or "", 0.0)
            trust_bonus = TRUST_BONUS.get(doc.source_trust_level, 0.0)
            final = (
                0.35 * keyword_score
                + 0.35 * vector_score
                + 0.15 * entity_bonus
                + 0.10 * trust_bonus
                + 0.05 * relation_bonus
            )
            results.append(RetrievalResult(
                chunk_id=chunk.id,
                document_id=doc.id,
                heritage_id=chunk.heritage_entity_id,
                title=doc.title,
                content=chunk.content,
                source_type=doc.source_type,
                source_trust_level=doc.source_trust_level,
                score=round(final, 4),
                score_breakdown={
                    "keyword": round(keyword_score, 4),
                    "vector": round(vector_score, 4),
                    "entity_bonus": entity_bonus,
                    "trust_bonus": trust_bonus,
                    "relation_bonus": relation_bonus,
                },
            ))
        results.sort(key=lambda item: item.score, reverse=True)
        final_results = results[: request.top_k]
        cache.set(cache_key, final_results)
        return final_results

    def _retrieve_with_postgres_vector(
        self,
        request: RetrievalRequest,
        terms: list[str],
        entity_ids: list[str],
        related: dict[str, float],
        search_entity_ids: list[str] | None,
    ) -> list[RetrievalResult]:
        if self.repo.count_embedding_vectors().get("embedded", 0) == 0:
            return []
        try:
            query_embedding = self.vector.embedding_provider.embed(request.query)
            vector_rows = self.repo.vector_search_chunks(
                query_embedding,
                entity_ids=search_entity_ids,
                limit=settings.vector_search_limit,
            )
        except Exception:
            return []
        keyword_rows = self.repo.keyword_search_chunks(
            " ".join(terms),
            entity_ids=search_entity_ids,
            limit=settings.vector_search_limit,
        )
        merged: dict[str, dict] = {}
        for row in vector_rows:
            merged[row["chunk_id"]] = {**row, "vector_score": float(row.get("vector_score") or 0.0), "keyword_score": 0.0}
        for row in keyword_rows:
            existing = merged.get(row["chunk_id"], {})
            merged[row["chunk_id"]] = {
                **row,
                **existing,
                "keyword_score": max(float(row.get("keyword_score") or 0.0), float(existing.get("keyword_score") or 0.0)),
                "vector_score": float(existing.get("vector_score") or 0.0),
            }
        results: list[RetrievalResult] = []
        for row in merged.values():
            if row["source_trust_level"] == "S4":
                continue
            keyword_score = min(1.0, float(row.get("keyword_score") or 0.0))
            if keyword_score == 0.0:
                keyword_score = self.keyword.score(terms, row["title"], row["content"])
            vector_score = float(row.get("vector_score") or 0.0)
            entity_bonus = 1.0 if row["heritage_entity_id"] in entity_ids else 0.0
            relation_bonus = related.get(row["heritage_entity_id"] or "", 0.0)
            trust_bonus = TRUST_BONUS.get(row["source_trust_level"], 0.0)
            final = (
                0.35 * keyword_score
                + 0.35 * vector_score
                + 0.15 * entity_bonus
                + 0.10 * trust_bonus
                + 0.05 * relation_bonus
            )
            results.append(
                RetrievalResult(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    heritage_id=row["heritage_entity_id"],
                    title=row["title"],
                    content=row["content"],
                    source_type=row["source_type"],
                    source_trust_level=row["source_trust_level"],
                    score=round(final, 4),
                    score_breakdown={
                        "keyword": round(keyword_score, 4),
                        "vector": round(vector_score, 4),
                        "entity_bonus": entity_bonus,
                        "trust_bonus": trust_bonus,
                        "relation_bonus": relation_bonus,
                    },
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return results[: request.top_k]
