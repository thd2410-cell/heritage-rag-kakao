"""프롬프트 조립 모듈.

CLAUDE.md 명세의 프롬프트 설계를 그대로 구현한다.
  - 한국어 해설 생성용 시스템 프롬프트
  - 다국어 번역용 시스템 프롬프트
탐지된 [용어 정의] 블록과 [원문]/[한국어 해설]을 끼워 넣어 완성한다.
"""

from __future__ import annotations

# 지원 언어 코드 -> LLM에 전달할 언어명
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "영어",
    "zh": "중국어",
    "ja": "일본어",
}


# ── 한국어 해설 시스템 프롬프트 (명세 그대로) ──────────────
_EXPLANATION_SYSTEM_TEMPLATE = """당신은 국가유산 전문 해설사입니다.

규칙:
1. 아래 [원문]을 바탕으로 해설하되, 사실을 절대 왜곡하거나 추가하지 않는다.
2. [용어 정의]에 있는 용어는 반드시 그 정의에 맞게 설명한다.
3. 일반 관람객이 이해할 수 있도록 자연스럽고 친근한 말투로 설명한다.
4. 역사적 사실, 연도, 인물명은 원문 그대로 유지한다.
5. 원문에 없는 내용은 절대 추가하지 않는다.

[용어 정의]
{term_definitions}

[원문]
{content}"""


# ── 다국어 번역 시스템 프롬프트 (명세 그대로) ──────────────
_TRANSLATION_SYSTEM_TEMPLATE = """당신은 한국 문화유산 전문 번역가입니다.

규칙:
1. 아래 [한국어 해설]을 {target_language}로 번역한다.
2. [용어 정의]를 참고하여 각 용어의 개념이 번역에서도 정확히 전달되도록 한다.
3. 단순 직역이 아닌, 해당 언어 문화권 독자가 자연스럽게 이해할 수 있도록 번역한다.
4. 고유명사(지명, 왕명, 유산명)는 괄호 안에 원어를 병기한다.
   예) 숭례문 (崇禮門, Sungnyemun)
5. 한국 고유 개념으로 직역이 어려운 용어는 간단한 설명을 괄호로 추가한다.

[용어 정의]
{term_definitions}

[한국어 해설]
{korean_explanation}"""


def _term_block_or_placeholder(term_definitions: str) -> str:
    """탐지된 용어가 없을 때를 위한 안전한 기본 문자열."""
    term_definitions = (term_definitions or "").strip()
    return term_definitions if term_definitions else "(해당 없음)"


def build_explanation_prompt(content: str, term_definitions: str) -> str:
    """한국어 해설 생성용 시스템 프롬프트를 조립한다.

    Args:
        content: 상세 API 해설 원문.
        term_definitions: term_extractor.build_term_context() 결과(여러 줄).
    """
    return _EXPLANATION_SYSTEM_TEMPLATE.format(
        term_definitions=_term_block_or_placeholder(term_definitions),
        content=(content or "").strip(),
    )


def build_translation_prompt(
    korean_explanation: str,
    term_definitions: str,
    target_lang: str,
) -> str:
    """다국어 번역용 시스템 프롬프트를 조립한다.

    Args:
        korean_explanation: 4단계에서 생성한 한국어 해설.
        term_definitions: 동일한 [용어 정의] 블록.
        target_lang: "en" | "zh" | "ja" (또는 SUPPORTED_LANGUAGES 키).
    """
    language_name = SUPPORTED_LANGUAGES.get(target_lang)
    if language_name is None:
        raise ValueError(
            f"지원하지 않는 언어 코드: '{target_lang}' "
            f"(가능: {', '.join(SUPPORTED_LANGUAGES)})"
        )
    return _TRANSLATION_SYSTEM_TEMPLATE.format(
        target_language=language_name,
        term_definitions=_term_block_or_placeholder(term_definitions),
        korean_explanation=(korean_explanation or "").strip(),
    )


# 해설 생성 시 user 메시지로 사용할 기본 지시문
EXPLANATION_USER_MESSAGE = "위 원문을 바탕으로 국가유산 해설을 작성해 주세요."
TRANSLATION_USER_MESSAGE = "위 한국어 해설을 규칙에 맞게 번역해 주세요."


# ── 후속 질문(대화형 Q&A) 시스템 프롬프트 ────────────────
_FOLLOWUP_SYSTEM_TEMPLATE = """당신은 국가유산 전문 해설사입니다. 사용자가 '{name}'에 대해 후속 질문을 합니다.

규칙:
1. 아래 [원문]과 [용어 정의]에 근거해서만 답한다. 사실을 왜곡하거나 원문에 없는 내용을 지어내지 않는다.
2. 원문에 답이 없으면 "제공된 자료에는 그 내용이 담겨 있지 않습니다"라고 솔직히 말한다.
3. [용어 정의]에 있는 용어는 반드시 그 정의에 맞게 설명한다.
4. 이전 대화 맥락을 고려해 "그 지붕", "그것" 같은 지시어가 무엇을 가리키는지 파악해 답한다.
5. 질문에 직접, 간결하고 친근하게 답한다. 해설 전체를 반복하지 않는다.{lang_rule}

[유산]
{name} {hanja}

[용어 정의]
{term_definitions}

[원문]
{content}

[이전 대화]
{history}"""

# 답변 언어 지시 (ko 가 아닐 때만 추가)
_FOLLOWUP_LANG_RULE = "\n6. 답변은 반드시 {language}로 작성한다. 고유명사는 괄호 안에 원어를 병기한다."


def _format_history(history: list[dict] | None) -> str:
    """대화 이력을 [이전 대화] 블록 문자열로 변환한다.

    history 항목 형식: {"q": 사용자질문, "a": 해설사답변}
    """
    if not history:
        return "(이전 대화 없음)"
    lines: list[str] = []
    for turn in history:
        q = (turn.get("q") or "").strip()
        a = (turn.get("a") or "").strip()
        if q:
            lines.append(f"사용자: {q}")
        if a:
            lines.append(f"해설사: {a}")
    return "\n".join(lines) if lines else "(이전 대화 없음)"


# ── RAG: 검색된 청크 근거 응답 ───────────────────────────
_RAG_SYSTEM_TEMPLATE = """당신은 국가유산 전문 해설사입니다. 아래 [검색된 자료]에 근거해서만 답합니다.
(참고: 유산 사진은 앱 화면이 당신의 답변과 함께 자동으로 보여줍니다. 그러니 "이미지를 보여드릴 수 없다", "직접 보여줄 수 없다" 같은 말은 절대 하지 말고, 사용자가 "보여줘"라고 하면 해당 유산을 설명만 하면 됩니다. 또한 답변에 '[검색된 자료]', 'N번', '청크' 같은 내부 구조 표현을 절대 드러내지 말고, 출처를 가리킬 때는 '자료에 따르면' 정도로만 자연스럽게 답하세요.)

규칙:
1. [검색된 자료]에 있는 사실만 사용한다. 자료에 없는 내용은 지어내지 말고 "제공된 자료에서는 확인되지 않습니다"라고 답한다.
2. 질문의 전제가 자료와 다르면, 자료에 근거해 정중히 바로잡는다. (예: 질문이 '폭설로 무너졌나?'인데 자료는 '방화 화재'라면, 폭설이 아니라 방화였음을 알려준다.)
3. 역사적 사실·연도·인물명을 왜곡하거나 추가하지 않는다.
4. [이전 대화]가 있으면 맥락을 고려해 '그것/그 둘/거기' 같은 지시어가 무엇을 가리키는지 파악해 답한다.
5. **간결하게 답한다.** 묻는 핵심에만 2~4문장으로 답하고, 사용자가 요청하지 않은 세부(연혁 전체·모든 특징 나열)는 늘어놓지 않는다. 표나 긴 불릿 목록은 사용자가 '자세히', '표로', '전부' 등을 명시적으로 요청할 때만 쓴다. 비교 질문도 가장 큰 차이 1~2가지만 먼저 짚는다.
6. 답변 끝의 추가 제안은 **질문 주제와 직접 이어질 때만** "~도 궁금하시면 알려드릴까요?" 처럼 한 문장으로 한다. 주제와 동떨어진 제안(예: 명칭의 유래를 물었는데 갑자기 현판 글씨를 권함)은 하지 말고, 마땅한 게 없으면 제안 없이 자연스럽게 끝낸다.
7. [검색된 자료]에 옛 문체나 한문 번역투(예: 'A曰B', '~이니', '~이라', '~하니')가 있으면 그대로 옮기지 말고 현대 한국어로 자연스럽게 풀어 쓴다. 특히 옛말의 '-이니/-이라'는 '때문에'(인과)가 아니라 '이고/이며'(나열·병렬 서술)인 경우가 많으니, 두 사실을 인과 관계로 곡해하지 않는다. 옛 기록을 인용할 때는 원문을 그대로 베끼기보다 '원문(또는 한자) + 현대어 뜻'을 함께 제시한다.{lang_rule}
{offer_block}{persona_block}{history_block}
[검색된 자료]
{context}"""

_RAG_LANG_RULE = "\n8. 답변은 반드시 {language}로 작성한다. 고유명사는 괄호 안에 원어를 병기한다."


def build_rag_prompt(
    context: str,
    lang: str = "ko",
    history: str | None = None,
    interests: list[str] | None = None,
    offer: list[str] | None = None,
) -> str:
    """검색된 청크 컨텍스트로 RAG 응답용 시스템 프롬프트를 조립한다.

    history(이전 대화 전사)가 있으면 [이전 대화] 블록을 포함해 멀티턴 맥락을 준다.
    interests(사용자 관심 분야)가 있으면 그 측면을 우선 설명하도록 살짝 유도한다.
    offer(관련 개별 유산)가 있으면, 질문 주제가 특정 유산이 아니라 상위 개념인 경우로 보고
        주제만 설명한 뒤 개별 유산을 '더 볼지' 제안하도록 한다(사진은 보류).
    """
    if lang != "ko":
        language_name = SUPPORTED_LANGUAGES.get(lang)
        if language_name is None:
            raise ValueError(f"지원하지 않는 언어 코드: '{lang}'")
        lang_rule = _RAG_LANG_RULE.format(language=language_name)
    else:
        lang_rule = ""
    history_block = f"\n[이전 대화]\n{history.strip()}\n" if history and history.strip() else ""
    persona_block = ""
    if interests:
        cats = ", ".join(interests)
        persona_block = (
            f"\n[사용자 관심 분야] {cats}\n"
            "(자료에 관련 내용이 있으면 이 분야와 연결지어 우선 설명하되, "
            "5번 규칙대로 간결함은 유지한다. 억지로 끼워넣지는 않는다.)\n"
        )
    offer_block = ""
    if offer:
        names = ", ".join(offer)
        offer_block = (
            f"\n[관련 개별 유산] {names}\n"
            "(이 질문의 주제는 특정 유산 하나가 아니라 여러 개별 유산을 아우르는 상위 개념입니다. "
            "먼저 주제 자체를 간결히 설명한 뒤, 답변 끝에서 위 개별 유산 중 하나를 자연스럽게 언급하며 "
            "'혹시 ○○도 궁금하시면 보여드릴까요?' 처럼 더 볼지 물어보세요.)\n"
        )
    return _RAG_SYSTEM_TEMPLATE.format(
        context=(context or "(검색 결과 없음)").strip(),
        lang_rule=lang_rule,
        history_block=history_block,
        persona_block=persona_block,
        offer_block=offer_block,
    )


# ── 멀티턴: 후속 질문 → 독립 검색어 재작성(condense) ──────
_CONDENSE_SYSTEM_TEMPLATE = """다음은 사용자와 국가유산 해설사의 이전 대화입니다. 마지막 사용자 질문에는 '그것', '그 둘', '거기', '아까 그' 처럼 이전 맥락을 가리키는 표현이 있을 수 있습니다.

마지막 질문을, 이전 대화를 모르는 사람도 이해할 수 있는 '독립적인 검색 질의' 한 문장으로 다시 쓰세요.

규칙:
1. 지시어를 구체적인 유산명/대상으로 바꾼다. (예: "그 둘 중 더 오래된 건?" → "숭례문과 수원 화성 중 더 오래된 것은?")
2. 검색에 필요한 핵심 키워드를 포함한다.
3. 이미 독립적인 질문이면 그대로 출력한다.
4. 다른 설명 없이 다시 쓴 질의 한 문장만 출력한다.

[이전 대화]
{history}

[마지막 질문]
{question}"""

CONDENSE_USER_MESSAGE = "위 마지막 질문을 독립적인 검색 질의 한 문장으로만 출력하세요."


def build_condense_prompt(history: str, question: str) -> str:
    """후속 질문을 독립 검색어로 재작성하기 위한 시스템 프롬프트."""
    return _CONDENSE_SYSTEM_TEMPLATE.format(
        history=(history or "").strip(), question=(question or "").strip()
    )


def format_chat(
    history: list[dict] | None, *, max_turns: int = 4, max_chars: int = 160
) -> str:
    """role 기반 메시지 목록을 '사용자/해설사' 전사 문자열로 변환한다.

    비용 절약: 최근 max_turns 턴만, 각 발화는 max_chars 로 잘라 입력 토큰을 줄인다.
    지시어 해석엔 최근 1~2턴이면 충분하다.

    history 항목: {"role": "user"|"bot", "text": ...}
    """
    if not history:
        return ""
    recent = history[-max_turns:]
    lines: list[str] = []
    for m in recent:
        text = (m.get("text") or "").strip()
        if not text:
            continue
        if len(text) > max_chars:
            text = text[:max_chars] + "…"
        who = "사용자" if m.get("role") == "user" else "해설사"
        lines.append(f"{who}: {text}")
    return "\n".join(lines)


# ── 용어 사전 자동 확장: 정의 생성 + SKIP 필터 ───────────
_TERM_DEFINITION_SYSTEM = """당신은 국가유산 용어 사전 편집자입니다. 후보 용어가 '국가유산·건축·불교·도자 등 분야의 일반 전문 용어'인지 판단하고, 맞다면 간결한 사전식 정의를 작성합니다.

규칙:
1. 후보가 특정 유산명·사건명·인물명·지명·연호 등 고유명사이면 정의하지 말고 정확히 "SKIP" 한 단어만 출력한다.
2. 일반 전문 용어이면 1~2문장의 간결한 정의를 출력한다. 관람객이 이해하기 쉬운 말투로 쓴다.
3. 정의는 해당 분야 일반 지식에 근거하되, 확실하지 않으면 한자 뜻과 문맥에서 추론 가능한 범위로만 보수적으로 작성한다.
4. 정의 외 다른 말(머리말, 따옴표, 용어명 반복, 'SKIP' 외 설명)은 출력하지 않는다.

[후보 용어]
{term} ({hanja})

[문맥]
{context}"""

TERM_DEFINITION_USER_MESSAGE = "위 후보에 대해 SKIP 또는 정의만 출력하세요."


def build_term_definition_prompt(term: str, hanja: str, context: str) -> str:
    """신규 용어 후보의 정의를 생성(또는 SKIP 판정)하기 위한 시스템 프롬프트."""
    return _TERM_DEFINITION_SYSTEM.format(
        term=term,
        hanja=hanja or "",
        context=(context or "").strip()[:400],  # 문맥은 앞부분만
    )


def build_followup_prompt(
    name: str,
    hanja: str,
    content: str,
    term_definitions: str,
    history: list[dict] | None,
    lang: str = "ko",
) -> str:
    """후속 질문 답변용 시스템 프롬프트를 조립한다.

    Args:
        name: 현재 유산 한글 명칭.
        hanja: 한자 명칭.
        content: grounding 원문(한국어).
        term_definitions: build_term_context() 결과.
        history: 이전 Q&A 이력.
        lang: 답변 언어 코드 (ko/en/zh/ja).
    """
    if lang != "ko":
        language_name = SUPPORTED_LANGUAGES.get(lang)
        if language_name is None:
            raise ValueError(f"지원하지 않는 언어 코드: '{lang}'")
        lang_rule = _FOLLOWUP_LANG_RULE.format(language=language_name)
    else:
        lang_rule = ""

    return _FOLLOWUP_SYSTEM_TEMPLATE.format(
        name=name,
        hanja=hanja or "",
        content=(content or "").strip(),
        term_definitions=_term_block_or_placeholder(term_definitions),
        history=_format_history(history),
        lang_rule=lang_rule,
    )


if __name__ == "__main__":
    sample_content = (
        "조선시대 한양도성의 정문으로, 돌을 쌓아 만든 석축 가운데에 "
        "무지개 모양의 홍예문을 두었다. 지붕은 우진각지붕이며 다포 양식이다."
    )
    sample_terms = (
        "- 홍예문: 반원 형태의 아치형 문...\n"
        "- 우진각지붕: 지붕의 네 면이 모두 경사진 형태...\n"
        "- 다포 양식: 기둥 사이에도 공포를 배치한 건축 양식..."
    )

    print("=" * 60)
    print("[해설 생성 프롬프트]")
    print("=" * 60)
    print(build_explanation_prompt(sample_content, sample_terms))

    print()
    print("=" * 60)
    print("[영어 번역 프롬프트]")
    print("=" * 60)
    print(build_translation_prompt("(한국어 해설 본문)", sample_terms, "en"))
