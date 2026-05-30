"""전체 파이프라인 조율 (1~5단계).

사용자 입력(유산 이름)을 받아 다음을 순서대로 수행한다.

  1단계: 목록 API   -> 유산 식별 (search_heritage)
  2단계: 상세 API   -> content(해설 원문), imageUrl (get_heritage_detail)
  3단계: 용어 레이어 -> 전문 용어 탐지 + [용어 정의] 컨텍스트 (term_extractor)
  4단계: LLM 해설   -> 왜곡 없는 한국어 해설 (prompt_builder + llm_api)
  5단계: 다국어 번역 -> 영/중/일 번역

결과로 HeritageResponse(해설/이미지/번역/메타)를 반환한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from api.heritage_api import (
    HeritageAPIError,
    HeritageDetail,
    get_heritage_detail,
    search_heritage,
)
from api.llm_api import call_llm
from core import prompt_builder
from core.term_extractor import TermDictionary, get_default_dictionary


@dataclass
class HeritageResponse:
    """챗봇이 사용자에게 돌려줄 최종 응답."""

    found: bool
    name: str = ""                       # 한글 명칭
    name_hanja: str = ""                 # 한자 명칭
    era: str = ""                        # 시대 정보
    location: str = ""                   # 소재지
    image_url: str = ""                  # 대표 이미지
    explanation: str = ""                # 4단계 한국어 해설
    translations: dict[str, str] = field(default_factory=dict)  # {언어코드: 번역}
    detected_terms: dict[str, str] = field(default_factory=dict)  # 탐지 용어
    source_content: str = ""             # 원문(검증/디버깅용)
    message: str = ""                    # 사용자 안내 메시지(미발견 등)


def run_pipeline(
    name: str,
    *,
    target_langs: Optional[list[str]] = None,
    ccba_kdcd: Optional[str] = None,
    dictionary: Optional[TermDictionary] = None,
    generate_explanation: bool = True,
) -> HeritageResponse:
    """유산 이름으로 전체 파이프라인을 실행한다.

    Args:
        name: 검색할 유산 이름 (예: "숭례문").
        target_langs: 번역 대상 언어 코드 목록. None이면 ["en"](Phase 1 기본).
        ccba_kdcd: 종목 코드로 검색을 좁히려면 지정.
        dictionary: 사용할 용어 사전. None이면 기본 싱글톤.
        generate_explanation: False면 1~3단계(API+용어)만 수행하고 LLM 호출은 생략.

    Returns:
        HeritageResponse.
    """
    if target_langs is None:
        target_langs = ["en"]  # Phase 1 MVP: 영어
    dictionary = dictionary or get_default_dictionary()

    # ── 1단계: 목록 검색 ──────────────────────────────
    results = search_heritage(name, ccba_kdcd=ccba_kdcd)
    if not results:
        return HeritageResponse(
            found=False,
            name=name,
            message=f"'{name}'에 해당하는 국가유산을 찾지 못했습니다. 이름을 다시 확인해 주세요.",
        )
    top = results[0]

    # ── 2단계: 상세 조회 ──────────────────────────────
    detail: HeritageDetail = get_heritage_detail(
        top.ccbaKdcd, top.ccbaAsno, top.ccbaCtcd
    )
    if not detail.content:
        return HeritageResponse(
            found=True,
            name=detail.ccbaMnm1 or top.ccbaMnm1,
            name_hanja=detail.ccbaMnm2,
            era=detail.ccceName,
            location=detail.ccbaLcad,
            image_url=detail.imageUrl,
            message="해설 원문이 제공되지 않는 유산입니다.",
        )

    # ── 3단계: 용어 레이어 ────────────────────────────
    detected_terms = dictionary.detect_terms(detail.content)
    term_context = dictionary.build_term_context(detail.content)

    response = HeritageResponse(
        found=True,
        name=detail.ccbaMnm1 or top.ccbaMnm1,
        name_hanja=detail.ccbaMnm2,
        era=detail.ccceName,
        location=detail.ccbaLcad,
        image_url=detail.imageUrl,
        detected_terms=detected_terms,
        source_content=detail.content,
    )

    if not generate_explanation:
        # LLM 없이 원문 기반 정보만 반환 (API 키 미설정 시 데모용)
        response.explanation = detail.content
        response.message = "(LLM 미사용: 해설 원문을 그대로 반환)"
        return response

    # ── 4단계: 한국어 해설 생성 ───────────────────────
    explanation_system = prompt_builder.build_explanation_prompt(
        detail.content, term_context
    )
    response.explanation = call_llm(
        explanation_system, prompt_builder.EXPLANATION_USER_MESSAGE
    )

    # ── 5단계: 다국어 번역 ────────────────────────────
    for lang in target_langs:
        translation_system = prompt_builder.build_translation_prompt(
            response.explanation, term_context, lang
        )
        response.translations[lang] = call_llm(
            translation_system, prompt_builder.TRANSLATION_USER_MESSAGE
        )

    return response


@dataclass
class LangResult:
    """특정 언어 1건에 대한 결과 (FastAPI 응답 매핑용)."""

    found: bool
    lang: str
    name: str = ""
    name_hanja: str = ""
    era: str = ""
    location: str = ""
    image_url: str = ""
    explanation: str = ""               # 요청 언어의 해설/번역 텍스트
    detected_terms: list[str] = field(default_factory=list)
    source_content: str = ""            # grounding 한국어 원문 (후속 질문용)
    note: str = ""                      # 안내 메시지 (LLM 미설정 등)
    message: str = ""                   # 미발견 등 사용자 메시지


def run_pipeline_for_lang(
    name: str,
    lang: str = "ko",
    *,
    ccba_kdcd: Optional[str] = None,
    dictionary: Optional[TermDictionary] = None,
) -> LangResult:
    """요청 언어 1건에 대한 결과를 만든다. (FastAPI 엔드포인트용)

    - lang="ko" : 4단계 한국어 해설 생성 (LLM 미설정 시 원문 그대로)
    - lang in {en,zh,ja} : 한국어 해설 -> 해당 언어 번역 (5단계)
      LLM 미설정 시에는 번역 불가 안내와 함께 한국어 원문을 제공한다.
    """
    from api.llm_api import is_configured

    configured, _ = is_configured()
    note = ""

    if lang == "ko":
        resp = run_pipeline(
            name,
            target_langs=[],
            ccba_kdcd=ccba_kdcd,
            dictionary=dictionary,
            generate_explanation=configured,
        )
        explanation = resp.explanation
        if not configured:
            note = "LLM 미설정: 해설 원문을 그대로 반환합니다. (.env에 API 키를 설정하세요)"
    else:
        if configured:
            resp = run_pipeline(
                name,
                target_langs=[lang],
                ccba_kdcd=ccba_kdcd,
                dictionary=dictionary,
                generate_explanation=True,
            )
            explanation = resp.translations.get(lang, "")
        else:
            # 번역 불가 -> 한국어 원문 제공 + 안내
            resp = run_pipeline(
                name,
                target_langs=[],
                ccba_kdcd=ccba_kdcd,
                dictionary=dictionary,
                generate_explanation=False,
            )
            explanation = resp.explanation
            note = "LLM 미설정으로 번역을 제공할 수 없어 한국어 원문을 반환합니다. (.env에 API 키를 설정하세요)"

    if not resp.found:
        return LangResult(found=False, lang=lang, name=name, message=resp.message)

    return LangResult(
        found=True,
        lang=lang,
        name=resp.name,
        name_hanja=resp.name_hanja,
        era=resp.era,
        location=resp.location,
        image_url=resp.image_url,
        explanation=explanation,
        detected_terms=list(resp.detected_terms.keys()),
        source_content=resp.source_content,
        note=note or resp.message,
    )


def answer_followup(
    name: str,
    content: str,
    question: str,
    *,
    hanja: str = "",
    lang: str = "ko",
    history: Optional[list[dict]] = None,
    dictionary: Optional[TermDictionary] = None,
) -> str:
    """현재 유산 원문(content)에 근거해 후속 질문에 답한다. (대화 맥락 유지)

    Args:
        name: 현재 유산 한글 명칭.
        content: grounding 원문(한국어). 프론트가 보관했다가 함께 전달.
        question: 사용자의 후속 질문.
        hanja: 한자 명칭(선택).
        lang: 답변 언어 (ko/en/zh/ja).
        history: 이전 Q&A 이력 [{"q":..,"a":..}, ...].
        dictionary: 용어 사전 (기본 싱글톤).

    Returns:
        해설사 답변 텍스트.
    """
    dictionary = dictionary or get_default_dictionary()
    term_context = dictionary.build_term_context(content)

    system = prompt_builder.build_followup_prompt(
        name=name,
        hanja=hanja,
        content=content,
        term_definitions=term_context,
        history=history,
        lang=lang,
    )
    return call_llm(system, question)


# 이미지 노출 기준: 최고 관련 유산과 코사인 유사도 격차가 이 값 이내인 유산만 표시.
# 작을수록 엄격(주제와 똑 떨어지는 유산만), 클수록 관대.
IMAGE_SIM_MARGIN = 0.07


@dataclass
class RagSource:
    """RAG 검색으로 사용된 청크 출처."""

    label: str            # '숭례문' 또는 '용어:홍예문'
    similarity: float
    snippet: str
    content: str = ""     # 근거 원문 전체(펼쳐보기용)
    refs: list = field(default_factory=list)  # 지식메모 출처 링크 [{label, url}]


@dataclass
class RagResult:
    answer: str
    sources: list[RagSource] = field(default_factory=list)
    image_url: str = ""           # (하위호환) 대표 이미지 1장
    image_name: str = ""          # 그 유산명
    images: list[dict] = field(default_factory=list)  # 등장한 유산별 이미지 [{name, url}]
    meta: dict = field(default_factory=dict)  # 로깅용: {condensed, answer_model, multi}


# 흔한 별칭 → 정식 유산명(부분) 매핑. 질문에 별칭이 나오면 해당 유산을 지목한 것으로 본다.
_HERITAGE_ALIASES = {
    "남대문": "숭례문",
    "동대문": "흥인지문",
}


def _detect_mentioned_heritages(question: str, names: set[str]) -> list[str]:
    """질문에 언급된(적재된) 유산명을 찾는다. 지역 접두어를 떼고도, 별칭으로도 매칭한다."""
    mentioned: list[str] = []
    for full in names:
        # "서울 숭례문" -> 후보 ["서울 숭례문", "숭례문"]
        candidates = {full}
        if " " in full:
            candidates.add(full.split(" ", 1)[1])
        if any(c and c in question for c in candidates):
            mentioned.append(full)
    # 별칭 처리 (예: "남대문" -> "서울 숭례문")
    for alias, core in _HERITAGE_ALIASES.items():
        if alias in question:
            for full in names:
                if core in full and full not in mentioned:
                    mentioned.append(full)
    return mentioned


# 이미지를 보여줄 '개요/식별/보기' 의도 신호
_IMAGE_INTENT_KW = (
    "설명", "소개", "알려", "어떤", "뭐야", "뭐니", "무엇", "보여", "사진",
    "이미지", "구경", "비교", "차이", "대해", "관해", "보고",
)


# 후속 질문에 '이전 맥락 참조(지시어)'가 있는지 — condense(재작성) 필요 여부 판단용
_ANAPHORA_RE = re.compile(
    r"(그것|그거|그게|그건|그곳|그들|그 [가-힣]|거기|저기|이거|이것|아까|방금|"
    r"위에|이전|둘\s?중|둘\s?다|나머지|다른\s|또\s|더\s|걔|얘)"
)


def _needs_condense(question: str) -> bool:
    """후속 질문을 독립 검색어로 재작성할 필요가 있는지 추정한다.

    - 지시어(그것/그 둘/거기/아까/더…)가 있거나
    - 질문이 매우 짧으면(맥락 의존 가능성) → 재작성 필요
    그 외(유산명을 직접 언급한 자족적 질문)는 재작성 없이 그대로 검색 → LLM 호출 절약.
    """
    q = (question or "").strip()
    if _ANAPHORA_RE.search(q):
        return True
    return len(re.sub(r"\s", "", q)) <= 6


_COMPARE_HINTS = ("비교", "차이", "이랑", "그리고", "vs", "대비")


def _is_multi_intent(question: str, mentioned: list[str]) -> bool:
    """여러 유산을 동시에 다루려는(비교/나열) 질문인지 추정한다."""
    if len(mentioned) >= 2:
        return True
    return any(k in (question or "") for k in _COMPARE_HINTS)


def _wants_image(question: str, mentioned: list[str]) -> bool:
    """질문이 '유산을 보여줄/소개할' 의도인지 추정한다.

    - 유산을 2개 이상 명시(나열/비교) → 보여주기
    - 개요/식별 키워드 포함 → 보여주기
    - 군더더기 없이 짧음(사실상 이름만, 예: "숭례문", "남대문") → 보여주기
    - 그 외(특정 사실 질문: "폭설로 무너졌어?", "언제 지어졌어?") → 보여주지 않음
    """
    if len(mentioned) >= 2:
        return True
    q = (question or "").strip()
    if any(k in q for k in _IMAGE_INTENT_KW):
        return True
    core = re.sub(r"[\s?!.,~]", "", q)
    return len(core) <= 7


def _hybrid_retrieve(question: str, q_vec, top_k: int):
    """벡터 + 이름 필터 + 키워드를 결합한 하이브리드 검색.

    1) 질문에 언급된 유산이 있으면 각 유산별로 균형 있게 청크 확보(이름 필터)
    2) 전역 벡터 검색으로 의미 유사 청크 보강
    3) 키워드(ILIKE) 매칭으로 누락 보강
    중복(content)은 제거하고, 이름 필터 → 벡터 → 키워드 순 우선순위로 병합한다.
    """
    from core import vector_store

    merged = []
    seen = set()

    def add(hits):
        for h in hits:
            if h.content in seen:
                continue
            seen.add(h.content)
            merged.append(h)

    names = vector_store.existing_heritage_names()
    mentioned = _detect_mentioned_heritages(question, names)

    # 1) 언급된 유산이 있으면 각 유산별로 균형 있게 청크 확보(이름 필터)
    if mentioned:
        per = max(3, top_k // len(mentioned))
        for hname in mentioned:
            add(vector_store.search(q_vec, top_k=per, heritage_name=hname))
    # 2) 전역 벡터 검색 — 부분만 명시된 비교 대상(예: "다보탑이랑 삼층석탑")도 포착
    add(vector_store.search(q_vec, top_k=top_k))
    # 3) 키워드(ILIKE) 보강
    tokens = [t for t in re.findall(r"[가-힣]{2,}", question)]
    if tokens:
        add(vector_store.keyword_search(tokens, limit=3))

    # 검색은 넓게 가져오고, '주제 유산' 추리기는 rag_answer 에서 한다.
    cap = top_k + 2 * len(mentioned) + 4
    return merged[:cap], mentioned


def rag_answer(
    question: str,
    *,
    lang: str = "ko",
    top_k: int = 5,
    history: Optional[list[dict]] = None,
    user_id: Optional[str] = None,
) -> RagResult:
    """질문을 임베딩→하이브리드 검색(벡터+이름+키워드)→상위 청크만 LLM에 주입해 답한다.

    멀티턴: history(이전 대화)가 있으면 지시어가 섞인 후속 질문을 독립 검색어로
    재작성(condense)한 뒤 검색하고, 생성 시 대화 맥락도 함께 준다.
    원문에 없는 내용은 LLM이 "확인되지 않습니다"로 답하도록 프롬프트로 강제한다.
    """
    from api.embeddings import embed_text

    history_text = prompt_builder.format_chat(history)

    # 0) 멀티턴 + 지시어가 있을 때만 후속 질문을 독립 검색어로 재작성(저렴한 모델 사용).
    #    유산명을 직접 언급한 자족적 후속은 재작성을 건너뛰어 LLM 호출을 아낀다.
    search_query = question
    did_condense = False
    if history_text and _needs_condense(question):
        did_condense = True
        try:
            from api.llm_api import light_model

            condense_system = prompt_builder.build_condense_prompt(history_text, question)
            rewritten = call_llm(
                condense_system,
                prompt_builder.CONDENSE_USER_MESSAGE,
                model=light_model(),
            ).strip()
            if rewritten:
                search_query = rewritten
        except Exception:
            # 재작성 실패 시 원 질문으로 검색
            search_query = question

    # 1) 검색어 임베딩
    q_vec = embed_text(search_query)

    # 2) 하이브리드 검색 (재작성된 검색어로 이름 감지/검색)
    hits, mentioned = _hybrid_retrieve(search_query, q_vec, top_k)
    if not hits:
        return RagResult(
            answer="제공된 자료에서는 확인되지 않습니다. (검색된 자료가 없습니다)",
            sources=[],
        )

    # 3) 유산별 최고 유사도 집계 → '주제 유산' 결정
    heritage_best: dict[str, dict] = {}  # 유산명 -> {sim, url}
    for h in hits:
        if h.source_type == "heritage" and h.similarity > 0:
            prev = heritage_best.get(h.heritage_name)
            if prev is None or h.similarity > prev["sim"]:
                heritage_best[h.heritage_name] = {"sim": h.similarity, "url": h.image_url}

    # 주제 유산 선정
    #   - 명시한 유산은 항상 주제
    #   - 비교 의도이거나(부분만 명시된 2번째 대상 포착), 명시가 아예 없을 때만
    #     최고 유사도 ±margin 유산을 추가한다. (단일 이름 질문은 그 유산만 → 곁다리 차단)
    subjects: set[str] = set(mentioned)
    if heritage_best and (not mentioned or _is_multi_intent(question, mentioned)):
        top_sim = max(v["sim"] for v in heritage_best.values())
        for name, v in heritage_best.items():
            if v["sim"] >= top_sim - IMAGE_SIM_MARGIN:
                subjects.add(name)

    # 4) 컨텍스트/출처/카테고리: 용어 청크 + 주제 유산 청크만 사용
    lines = []
    sources: list[RagSource] = []
    hit_categories: list[str] = []
    focused = [
        h for h in hits if h.source_type == "term" or h.heritage_name in subjects
    ]
    for i, h in enumerate(focused, 1):
        # 지식메모는 끝에 붙은 출처 마커를 분리(LLM·컨텍스트에는 본문만, 출처는 링크로)
        body = h.content
        refs: list = []
        if h.source_type == "note" and "\n[[SOURCES]]" in body:
            body, _, raw = body.partition("\n[[SOURCES]]")
            body = body.strip()
            try:
                refs = json.loads(raw)
            except Exception:
                refs = []

        if h.source_type == "term":
            label = f"용어:{h.term}"
        elif h.source_type == "note":
            label = f"{h.heritage_name or ''} · 지식메모".strip(" ·")
        else:
            label = h.heritage_name or "유산"
        lines.append(f"{i}. [{label}] {body}")
        sources.append(
            RagSource(
                label=label,
                similarity=round(h.similarity, 4),
                snippet=body[:60],
                content=body,
                refs=refs,
            )
        )
        if h.source_type == "heritage" and h.similarity > 0 and h.category:
            hit_categories.append(h.category)  # 개인화 가중치용
    context = "\n".join(lines)

    # 5) 이미지 vs 제안 결정
    #   - 상위 개념(이름 명시 없이 여러 유산으로 갈라짐, 예: "원각사") → 이미지 보류 + 개별 유산 제안
    #   - 그 외에는 '보여줄 의도'일 때만 이미지 표시
    #       · 개요/식별/비교/보기 의도("숭례문", "남대문", "설명해줘", "A랑 B 비교") → 표시
    #       · 특정 사실 질문("폭설로 무너졌어?", "언제 지어졌어?") → 답만, 이미지 없음
    subj_ranked = [
        n
        for n in sorted(
            subjects, key=lambda n: heritage_best.get(n, {}).get("sim", 0.0), reverse=True
        )
        if n in heritage_best
    ]
    offer: list[str] = []
    images = []
    parent_concept = (not mentioned) and len(subj_ranked) >= 2
    if parent_concept:
        offer = subj_ranked[:3]  # 답변 끝에 제안할 개별 유산
    elif subj_ranked and _wants_image(question, mentioned):
        images = [
            {"name": n, "url": heritage_best[n]["url"]}
            for n in subj_ranked
            if heritage_best[n]["url"]
        ][:4]

    # 4) 개인화: 이번 답변은 '과거에 쌓인' 관심사로 맞춤, 학습은 답변 뒤에
    interests: list[str] = []
    if user_id:
        from core import user_store

        interests = [c for c, _ in user_store.top_interests(user_id, n=3)]

    # 6) grounded 응답 생성 (대화 맥락 + 관심사 + 상위개념 제안 포함)
    #    비용 최적화: 비교/상위개념(합성·제안 필요)은 기본 모델, 단순 단일 질문은 저렴 모델.
    from api.llm_api import default_model, light_model

    use_full = _is_multi_intent(question, mentioned) or bool(offer)
    answer_model = None if use_full else light_model()
    system = prompt_builder.build_rag_prompt(
        context, lang, history=history_text, interests=interests, offer=offer
    )
    answer = call_llm(system, question, model=answer_model)

    # 6) 이번 질문에서 검색된 카테고리로 관심 가중치 누적 (다음 턴부터 반영)
    if user_id and hit_categories:
        from core import user_store

        user_store.bump_interests(user_id, hit_categories)

    return RagResult(
        answer=answer,
        sources=sources,
        image_url=images[0]["url"] if images else "",
        image_name=images[0]["name"] if images else "",
        images=images,
        meta={
            "condensed": did_condense,
            "answer_model": answer_model or default_model(),
            "multi": use_full,
        },
    )


@dataclass
class AddedTerm:
    """자동 확장으로 사전에 추가된 용어."""

    term: str
    hanja: str
    definition: str


def expand_dictionary_from_content(
    content: str,
    *,
    max_new: int = 5,
    dictionary: Optional[TermDictionary] = None,
) -> list[AddedTerm]:
    """원문에서 사전에 없는 `단어(한자)` 후보를 찾아 LLM 정의를 생성·등록한다.

    LLM이 고유명사(유산명/사건명/인물명 등)로 판단하면 'SKIP' 하여 추가하지 않는다.
    실제 일반 전문 용어만 사전에 누적된다.

    Args:
        content: 해설 원문.
        max_new: 한 번에 처리할 신규 후보 최대 수 (LLM 비용 제한).
        dictionary: 대상 사전 (기본 싱글톤).

    Returns:
        새로 추가된 AddedTerm 목록.
    """
    dictionary = dictionary or get_default_dictionary()
    candidates = dictionary.unknown_hanja_terms(content)[:max_new]

    added: list[AddedTerm] = []
    for cand in candidates:
        ctx = dictionary.context_for(cand.korean, content)
        system = prompt_builder.build_term_definition_prompt(
            cand.korean, cand.hanja, ctx
        )
        try:
            raw = call_llm(system, prompt_builder.TERM_DEFINITION_USER_MESSAGE).strip()
        except Exception:
            # 개별 용어 실패는 무시하고 나머지 진행
            continue

        # SKIP 판정 (고유명사 등)
        if not raw or raw.upper().startswith("SKIP"):
            continue
        # "용어: 정의" 형태로 오면 머리말 제거
        definition = raw
        prefix = f"{cand.korean}:"
        if definition.startswith(prefix):
            definition = definition[len(prefix):].strip()

        if dictionary.add_term(cand.korean, definition):
            added.append(
                AddedTerm(term=cand.korean, hanja=cand.hanja, definition=definition)
            )

    return added


if __name__ == "__main__":
    from api.llm_api import is_configured

    ok, info = is_configured()
    print(f"[LLM] {info}\n")

    # API 키가 없으면 1~3단계만(generate_explanation=False) 실행해 동작 검증
    resp = run_pipeline("숭례문", generate_explanation=ok, target_langs=["en"])

    print(f"발견 여부 : {resp.found}")
    print(f"명칭      : {resp.name} ({resp.name_hanja})")
    print(f"시대      : {resp.era}")
    print(f"소재지    : {resp.location}")
    print(f"이미지    : {resp.image_url}")
    print(f"탐지 용어 : {list(resp.detected_terms)}")
    if resp.message:
        print(f"안내      : {resp.message}")
    print("\n[해설]")
    print(resp.explanation[:300], "..." if len(resp.explanation) > 300 else "")
    for lang, text in resp.translations.items():
        print(f"\n[번역:{lang}]")
        print(text[:300], "..." if len(text) > 300 else "")
