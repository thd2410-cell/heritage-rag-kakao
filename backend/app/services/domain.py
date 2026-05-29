DOMAIN_KEYWORDS = [
    "국가유산", "문화재", "문화유산", "유적", "유물", "궁", "궁궐", "왕릉", "사찰", "절",
    "국보", "보물", "사적", "명승", "천연기념물", "민속문화유산", "등록유산", "경복궁", "창덕궁",
    "첨성대", "석굴암", "불국사", "수막새", "경주", "조선", "신라", "백제", "고려", "유산",
    "역사", "왕", "인물", "사건", "퀴즈", "추천",
]

OUT_OF_DOMAIN_MESSAGE = "저는 국가유산 전문 AI 해설사입니다.\n국가유산, 문화재, 유적, 유물과 관련된 질문을 부탁드립니다."


def is_heritage_domain(text: str) -> bool:
    compact = (text or "").strip().lower()
    return any(keyword.lower() in compact for keyword in DOMAIN_KEYWORDS)
