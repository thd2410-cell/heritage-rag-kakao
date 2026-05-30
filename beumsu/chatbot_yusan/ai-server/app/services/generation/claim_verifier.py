import re

from app.schemas.chat import Citation
from app.schemas.retrieval import RetrievalResult


class ClaimVerifier:
    def verify(self, answer: str, citations: list[Citation], evidence: list[RetrievalResult], intent: str, language: str, audience: str) -> dict:
        issues = []
        if not citations:
            issues.append("missing_citations")
        if intent in {"heritage_explanation", "child_explanation", "expert_explanation", "glossary_question"}:
            if citations and all(c.source_trust_level not in {"S1", "S2"} for c in citations):
                issues.append("insufficient_source_trust")
        evidence_text = " ".join(e.content for e in evidence)
        for year in re.findall(r"\d{3,4}\s*년?", answer):
            canonical_year = year.replace(" ", "")
            if canonical_year not in evidence_text:
                issues.append(f"unsupported_year:{canonical_year}")
        known_terms = ["경복궁", "근정전", "경회루", "향원정", "창덕궁", "창경궁", "덕수궁", "종묘", "조선"]
        for term in known_terms:
            if term in answer and term not in evidence_text and not any(term in c.title for c in citations):
                issues.append(f"unsupported_entity:{term}")
        return {"passed": not issues, "issues": issues, "revised_answer_required": bool(issues)}
