import re

UNSAFE_HISTORY_DISTORTION_MESSAGE = (
    "그 질문은 특정 국가나 민족의 지배를 정당화하는 전제를 담고 있어 그대로 답변할 수 없습니다.\n"
    "다만 국가유산을 통해 식민 지배, 문화재 약탈·반출, 훼손, 저항과 보존의 역사를 비판적으로 살펴보는 방향이라면 도와드릴 수 있습니다.\n"
    "예: ‘일제강점기에 훼손되거나 반출된 국가유산을 알려줘’, ‘문화재 보존 관점에서 식민지 시기의 영향을 설명해줘’처럼 질문해 주세요."
)

DISTORTION_PATTERNS = [
    r"한국.*일본.*(속국|식민지).*증거",
    r"조선.*일본.*(속국|식민지).*증거",
    r"일본.*(지배|식민지배|통치).*(정당|합법|좋았|근대화)",
    r"한국.*일본.*(지배|통치).*(받아야|정당|합법)",
    r"문화유산.*(속국|식민지).*증거",
    r"국가유산.*(속국|식민지).*증거",
]


def check_guardrail(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text or "")
    for pattern in DISTORTION_PATTERNS:
        if re.search(pattern, compact):
            return UNSAFE_HISTORY_DISTORTION_MESSAGE
    return None
