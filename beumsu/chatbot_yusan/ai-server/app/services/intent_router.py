from dataclasses import dataclass


@dataclass
class IntentResult:
    intent: str
    output_language: str | None = None
    audience: str | None = None


class IntentRouter:
    def route(self, query: str, language: str, audience: str) -> IntentResult:
        q = query.lower()
        if any(x in q for x in ["폭탄", "bomb", "system prompt", "ignore previous", "출처 무시", "근거 없이"]):
            return IntentResult("unsafe", language, audience)
        if any(x in q for x in ["코스", "route", "course", "1시간", "60분", "동선"]):
            return IntentResult("route_recommendation", language, audience)
        if any(x in q for x in ["아이", "어린이", "kids", "child"]):
            return IntentResult("child_explanation", language, "child")
        if any(x in q for x in ["전문", "건축 양식", "expert"]):
            return IntentResult("expert_explanation", language, "expert")
        if any(x in q for x in ["음성", "읽어줘", "시각장애", "청각장애"]):
            return IntentResult("accessibility_request", language, audience)
        if any(x in q for x in ["뭐야", "what is", "glossary", "단청"]):
            return IntentResult("glossary_question", language, audience)
        if "english" in q or " in english" in q:
            return IntentResult("heritage_explanation", "en", audience)
        return IntentResult("heritage_explanation", language, audience)
