from app.services.guardrails.prompt_injection import detect_prompt_injection


class InputGuardrail:
    def check(self, query: str) -> dict:
        flags = []
        if detect_prompt_injection(query):
            flags.append("prompt_injection")
        if any(word in query.lower() for word in ["폭탄", "bomb", "kill", "테러"]):
            flags.append("unsafe_violence")
        if "중국 궁궐" in query and ("출처 무시" in query or "근거 없이" in query):
            flags.append("historical_distortion_attempt")
        return {"blocked": bool(flags), "flags": flags}
