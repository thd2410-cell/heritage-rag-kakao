from pydantic import BaseModel, Field


class AudienceProfile(BaseModel):
    age_group: str | None = Field(default=None, description="예: elementary, middle_high, adult, senior")
    interests: list[str] = Field(default_factory=list, description="예: architecture, story, people, travel, quiz")


AGE_GROUP_LABELS = {
    "elementary": "초등학생",
    "middle_high": "중고등학생",
    "adult": "성인",
    "senior": "시니어",
}

INTEREST_LABELS = {
    "architecture": "건축과 공간",
    "story": "이야기와 전설",
    "people": "역사 인물",
    "travel": "답사와 여행",
    "quiz": "퀴즈와 학습",
}


def build_audience_instruction(profile: AudienceProfile | None) -> str:
    if not profile:
        return "대상 정보: 일반 방문자. 너무 어렵지 않은 한국어로 설명한다."

    age = AGE_GROUP_LABELS.get(profile.age_group or "", "일반 방문자")
    interests = [INTEREST_LABELS.get(item, item) for item in profile.interests if item]
    interest_text = ", ".join(interests) if interests else "특정 관심사 없음"

    tone_by_age = {
        "elementary": "짧은 문장과 쉬운 낱말을 사용하고, 어려운 말은 바로 풀어쓴다.",
        "middle_high": "교과서식 핵심 개념과 사건의 원인·결과를 함께 설명한다.",
        "adult": "핵심 정보와 역사적 의미를 균형 있게 설명한다.",
        "senior": "천천히 읽기 좋은 문장으로, 장소·시대·의미를 분명히 설명한다.",
    }.get(profile.age_group or "", "너무 어렵지 않은 한국어로 설명한다.")

    return (
        f"대상 정보: {age}. 관심사: {interest_text}.\n"
        f"대상 맞춤 방식: {tone_by_age}\n"
        "개인화 규칙: 관심사는 설명의 비유, 강조점, 후속 질문을 고르는 데만 사용한다. "
        "검색 근거에 없는 체험 프로그램, 퀴즈 제공 여부, 전설, 장소 정보, 현재 위치를 절대 새로 만들지 않는다.\n"
        "답변 마지막에는 검색 근거에서 확인 가능한 내용만 바탕으로, 사용자의 나이대와 관심사에 맞는 후속 질문 2개를 '다음에 물어볼 만한 질문'으로 제안한다."
    )
