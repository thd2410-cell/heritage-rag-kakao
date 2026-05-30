from __future__ import annotations

import time
from uuid import uuid4

from app.core.config import settings
from app.db.repository import HeritageRepository
from app.schemas.chat import ChatRequest, ChatResponse, ImageAsset
from app.schemas.retrieval import RetrievalRequest
from app.schemas.route import Mobility, RouteRecommendationInput
from app.services.entity_normalizer import EntityNormalizer
from app.services.generation.answer_generator import AnswerGenerator
from app.services.generation.claim_verifier import ClaimVerifier
from app.services.generation.llm_provider import build_llm_provider
from app.services.guardrails.input_guardrail import InputGuardrail
from app.services.guardrails.output_guardrail import OutputGuardrail
from app.services.intent_router import IntentRouter
from app.services.retrieval.hybrid_retriever import HybridRetriever
from app.services.retrieval.reranker import MockReranker
from app.services.route.route_planner import RoutePlanner
from app.services.translation.language_detector import LanguageDetector


class ChatOrchestrator:
    def __init__(self, repo: HeritageRepository):
        self.repo = repo
        self.input_guardrail = InputGuardrail()
        self.output_guardrail = OutputGuardrail()
        self.language_detector = LanguageDetector()
        self.normalizer = EntityNormalizer(repo)
        self.intent_router = IntentRouter()
        self.retriever = HybridRetriever(repo)
        self.reranker = MockReranker()
        self.generator = AnswerGenerator(
            build_llm_provider(
                settings.llm_provider,
                api_key=settings.openai_api_key,
                model=settings.openai_model,
            )
        )
        self.verifier = ClaimVerifier()
        self.route_planner = RoutePlanner()

    def chat(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        safety = self.input_guardrail.check(request.query)
        if safety["blocked"]:
            return ChatResponse(
                answer="요청에 안전하지 않거나 근거 기반 답변 원칙을 우회하려는 내용이 포함되어 답변할 수 없습니다.",
                normalized_query=request.query,
                detected_language=self.language_detector.detect(request.query, request.language),
                intent="unsafe",
                safety_flags=safety["flags"],
                latency_ms=self._latency(started),
            )
        language = self.language_detector.detect(request.query, request.language)
        normalized = self.normalizer.normalize(request.query)
        intent = self.intent_router.route(request.query, language, request.audience)
        output_language = intent.output_language or language
        audience = intent.audience or request.audience
        if intent.intent == "route_recommendation":
            route_input = RouteRecommendationInput(
                start="광화문",
                duration_minutes=60,
                audience=audience,
                mobility=Mobility(minimize_walking=audience == "elderly"),
            )
            entity_id = normalized.detected_entities[0].heritage_id if normalized.detected_entities else "gyeongbokgung"
            route = self.route_planner.plan(entity_id, route_input)
            evidence = self._retrieve_for_entities([s["heritage_id"] for s in route["stops"] if s["heritage_id"]])
            route_entity_ids = [s["heritage_id"] for s in route["stops"] if s["heritage_id"]]
            generated = self.generator.generate(request.query, output_language, audience, normalized.detected_entities, evidence)
            return ChatResponse(
                answer=generated["answer"],
                normalized_query=normalized.normalized_text,
                detected_language=language,
                intent=intent.intent,
                entities=normalized.detected_entities,
                citations=generated["citations"],
                confidence=generated["confidence"],
                follow_up_questions=generated["follow_up_questions"],
                images=self._image_assets(route_entity_ids),
                route=route,
                safety_flags=[],
                latency_ms=self._latency(started),
            )
        retrieval_request = RetrievalRequest(
            query=normalized.normalized_text,
            normalized_entities=normalized.detected_entities,
            language=output_language,
            intent=intent.intent,
            audience=audience,
        )
        results = self.retriever.retrieve(retrieval_request)
        selected_ids = [e.heritage_id for e in normalized.detected_entities]
        evidence = self.reranker.rerank(normalized.normalized_text, results, selected_ids)[:5]
        image_entity_ids = selected_ids or [item.heritage_id for item in evidence if item.heritage_id]
        generated = self.generator.generate(request.query, output_language, audience, normalized.detected_entities, evidence)
        verification = self.verifier.verify(generated["answer"], generated["citations"], evidence, intent.intent, output_language, audience)
        if not verification["passed"]:
            generated["answer"] = self._fallback(evidence)
            verification = self.verifier.verify(generated["answer"], generated["citations"], evidence, intent.intent, output_language, audience)
        output_safety = self.output_guardrail.check(generated["answer"], generated["citations"])
        if output_safety["blocked"]:
            generated["answer"] = "확인된 공식 근거만으로는 충분히 답변하기 어렵습니다."
        response = ChatResponse(
            answer=generated["answer"],
            normalized_query=normalized.normalized_text,
            detected_language=language,
            intent=intent.intent,
            entities=normalized.detected_entities,
            citations=generated["citations"] if request.options.include_citations else [],
            images=self._image_assets(image_entity_ids),
            confidence=generated["confidence"],
            follow_up_questions=generated["follow_up_questions"],
            route=None,
            safety_flags=output_safety["flags"],
            latency_ms=self._latency(started),
        )
        self.repo.db.info.setdefault("conversation_logs", []).append({
            "id": str(uuid4()),
            "query": request.query,
            "normalized_query": response.normalized_query,
            "intent": response.intent,
            "latency_ms": response.latency_ms,
        })
        return response

    def _retrieve_for_entities(self, entity_ids: list[str]):
        class E:
            def __init__(self, heritage_id: str):
                self.heritage_id = heritage_id
                self.official_name_ko = heritage_id
        return self.retriever.retrieve(RetrievalRequest(query=" ".join(entity_ids), normalized_entities=[E(e) for e in entity_ids], top_k=8))

    def _image_assets(self, entity_ids: list[str]) -> list[ImageAsset]:
        seen: set[str] = set()
        unique_ids = []
        for entity_id in entity_ids:
            if entity_id and entity_id not in seen:
                seen.add(entity_id)
                unique_ids.append(entity_id)
        return [
            ImageAsset(
                image_id=row.id,
                heritage_id=row.heritage_entity_id,
                title=row.title,
                image_url=row.image_url,
                thumbnail_url=row.thumbnail_url,
                caption=row.caption,
                license_type=row.license_type,
                source_uri=row.source_uri,
                source_trust_level=row.source_trust_level,
            )
            for row in self.repo.list_images_for_entities(unique_ids)
        ]

    def _fallback(self, evidence) -> str:
        if not evidence:
            return "확인된 공식 근거만으로는 충분히 답변하기 어렵습니다."
        return "확인된 공식 근거만으로는 충분히 답변하기 어렵습니다. 현재 확인 가능한 내용은 다음과 같습니다: " + evidence[0].content

    def _latency(self, started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
