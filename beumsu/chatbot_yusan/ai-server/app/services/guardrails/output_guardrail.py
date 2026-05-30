from app.schemas.chat import Citation


class OutputGuardrail:
    def check(self, answer: str, citations: list[Citation]) -> dict:
        flags = []
        lowered = answer.lower()
        if "system prompt" in lowered or "openai_api_key" in lowered or "traceback" in lowered:
            flags.append("internal_leak")
        if not citations and any(term in answer for term in ["조선", "궁궐", "왕실", "의례"]):
            flags.append("uncited_historical_claim")
        return {"blocked": bool(flags), "flags": flags}
