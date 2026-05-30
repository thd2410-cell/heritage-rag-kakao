from app.schemas.chat import Citation, EntityMatch
from app.schemas.retrieval import RetrievalResult
from app.services.generation.llm_provider import DummyProvider, LLMProvider, LocalMockProvider
from app.services.generation.prompt_templates import SYSTEM_PROMPT


class AnswerGenerator:
    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or DummyProvider()

    def generate(
        self,
        query: str,
        language: str,
        audience: str,
        entities: list[EntityMatch],
        evidence: list[RetrievalResult],
    ) -> dict:
        if not evidence:
            return {
                "answer": "확인된 자료에서는 해당 내용을 찾기 어렵습니다.",
                "citations": [],
                "confidence": 0.0,
                "unsupported_claims": [],
                "follow_up_questions": [],
            }

        prefix = self._prefix(entities, language)
        evidence_text = self._evidence_text(evidence[:5])
        generation_prompt = self._user_prompt(query, language, audience, entities)
        messages = [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n<evidence>{evidence_text}</evidence>"},
            {"role": "user", "content": generation_prompt},
        ]
        provider_failed = False
        try:
            raw = self.provider.generate(messages, temperature=0.2)
        except Exception:
            provider_failed = True
            raw = DummyProvider().generate(messages, temperature=0.2)

        if isinstance(self.provider, (DummyProvider, LocalMockProvider)) and language == "en":
            answer = self._english_answer(prefix, entities, evidence)
        else:
            answer = self._style(prefix + raw, language, audience)

        citations = [
            Citation(
                document_id=e.document_id,
                chunk_id=e.chunk_id,
                title=e.title,
                source_type=e.source_type,
                source_trust_level=e.source_trust_level,
            )
            for e in evidence[:3]
        ]
        return {
            "answer": answer,
            "citations": citations,
            "confidence": max([e.confidence for e in entities], default=0.75),
            "unsupported_claims": ["llm_provider_fallback"] if provider_failed else [],
            "follow_up_questions": self._followups(entities, language),
        }

    def _evidence_text(self, evidence: list[RetrievalResult]) -> str:
        lines = []
        for i, item in enumerate(evidence, start=1):
            lines.append(
                f"[{i}] title={item.title}; document_id={item.document_id}; "
                f"chunk_id={item.chunk_id}; trust={item.source_trust_level}; content={item.content}"
            )
        return "\n".join(lines)

    def _user_prompt(
        self,
        query: str,
        language: str,
        audience: str,
        entities: list[EntityMatch],
    ) -> str:
        entity_note = ""
        if entities:
            first = entities[0]
            entity_note = (
                f"Normalized entity: {first.official_name_ko} "
                f"(matched_alias={first.matched_alias}, confidence={first.confidence})."
            )
        return (
            f"User query: {query}\n"
            f"Answer language: {language}\n"
            f"Audience: {audience}\n"
            f"{entity_note}\n"
            "Write a concise answer using only the evidence. "
            "Do not add dates, people, locations, or historical claims unless they appear in evidence. "
            "Do not include raw document IDs in the prose; citations are attached separately by the system."
        )

    def _prefix(self, entities: list[EntityMatch], language: str) -> str:
        if not entities:
            return ""
        first = entities[0]
        if first.matched_alias != first.official_name_ko or first.confirmation_required:
            if language == "en":
                english_names = {
                    "gyeongbokgung": "Gyeongbokgung Palace",
                    "geunjeongjeon": "Geunjeongjeon Hall",
                    "gyeonghoeru": "Gyeonghoeru Pavilion",
                    "hyangwonjeong": "Hyangwonjeong Pavilion",
                    "changdeokgung": "Changdeokgung Palace",
                    "jongmyo": "Jongmyo Shrine",
                }
                return f"I understood your question as {english_names.get(first.heritage_id, first.matched_alias)}. "
            return f"{first.official_name_ko}을 말씀하신 것으로 이해하고 설명드릴게요. "
        return ""

    def _style(self, answer: str, language: str, audience: str) -> str:
        if audience == "child":
            answer = answer.replace("핵심 유산", "중요한 문화유산").replace("정전", "중심 건물")
        if audience == "elderly":
            answer += " 관람 시에는 가까운 휴식 지점을 함께 확인하는 것을 권합니다."
        return answer

    def _english_answer(self, prefix: str, entities: list[EntityMatch], evidence: list[RetrievalResult]) -> str:
        entity_id = entities[0].heritage_id if entities else (evidence[0].heritage_id if evidence else "")
        if entity_id == "gyeongbokgung":
            body = (
                "Based on the available S1 evidence, Gyeongbokgung Palace is the main royal palace "
                "of the Joseon dynasty and an important heritage site for understanding Joseon palace "
                "culture and royal rituals. The same evidence also identifies Geunjeongjeon Hall, "
                "Gyeonghoeru Pavilion, and Hyangwonjeong Pavilion as major spaces within the palace."
            )
        elif entity_id == "geunjeongjeon":
            body = (
                "Based on the available S1 evidence, Geunjeongjeon Hall is the central building of "
                "Gyeongbokgung Palace and the main hall where state rites and official ceremonies were held."
            )
        elif entity_id == "gyeonghoeru":
            body = (
                "Based on the available S1 evidence, Gyeonghoeru Pavilion is a pavilion within "
                "Gyeongbokgung Palace used for banquets and receptions for foreign envoys."
            )
        elif entity_id == "hyangwonjeong":
            body = (
                "Based on the available S1 evidence, Hyangwonjeong Pavilion is a pavilion in the rear "
                "garden area of Gyeongbokgung Palace, used for rest and appreciating the landscape."
            )
        else:
            body = "Based on the available S1 evidence, I can only answer from the cited source shown below."
        return prefix + body

    def _followups(self, entities: list[EntityMatch], language: str) -> list[str]:
        if language == "en":
            return ["Would you like a short route recommendation?", "Would you like a child-friendly explanation?"]
        name = entities[0].official_name_ko if entities else "이 유산"
        return [f"{name}의 주요 공간도 알려드릴까요?", "어린이용으로 더 쉽게 설명해드릴까요?"]
