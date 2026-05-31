"""
retriever.py — 사용자 질문을 받아 RAG로 답변 생성
질문할 때마다 실행 가능.

실행: python rag/retriever.py
"""
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_core.embeddings import Embeddings
from openai import OpenAI
from sentence_transformers import SentenceTransformer

# .env 파일 자동 로드 (OPENAI_API_KEY)
load_dotenv()


# ─────────────────────────────────────────────────────────
# 1. 임베딩 모델 (indexer.py와 동일해야 함!)
# ─────────────────────────────────────────────────────────
class KoSimCSEEmbeddings(Embeddings):
    def __init__(self):
        print("임베딩 모델 로딩 중...")
        self.model = SentenceTransformer("BM-K/KoSimCSE-roberta")

    def embed_documents(self, texts):
        return self.model.encode(texts).tolist()

    def embed_query(self, text):
        return self.model.encode([text])[0].tolist()


# ─────────────────────────────────────────────────────────
# 2. ChromaDB 불러오기
# ─────────────────────────────────────────────────────────
base = Path(__file__).parent.parent
vectorstore = Chroma(
    persist_directory=str(base / "chroma_db"),
    embedding_function=KoSimCSEEmbeddings(),
    collection_name="heritages",
)

# ─────────────────────────────────────────────────────────
# 3. OpenAI 클라이언트
#    .env의 OPENAI_API_KEY를 자동으로 읽음
# ─────────────────────────────────────────────────────────
client = OpenAI()


def answer(question: str, k: int = 3) -> str:
    """
    질문을 받아 RAG로 답변 생성

    1) 질문을 벡터로 변환
    2) ChromaDB에서 가장 유사한 chunk k개 검색
    3) 그 chunk들을 GPT에게 컨텍스트로 전달
    4) GPT가 컨텍스트 기반 답변 생성
    """

    # 1) + 2) 검색
    docs = vectorstore.similarity_search(question, k=k)

    if not docs:
        return "해당 국가유산 정보를 찾지 못했어요."

    # 디버그용: 어떤 chunk가 검색됐는지 확인
    print("\n[검색된 chunk]")
    for i, doc in enumerate(docs, 1):
        preview = doc.page_content[:80].replace("\n", " ")
        print(f"  {i}. {preview}...")

    # 3) 컨텍스트 합치기
    context = "\n\n---\n\n".join([doc.page_content for doc in docs])

    # 4) GPT 호출
    system_prompt = (
        "당신은 국가유산청 공식 데이터를 기반으로 안내하는 친근한 AI 해설사입니다.\n"
        "반드시 아래 [참고 자료]에 있는 내용만 근거로 답변하세요.\n"
        "참고 자료에 없는 내용은 \"해당 정보가 없습니다\"라고 답하세요.\n"
        "답변은 친근하지만 정확하게, 4~6문장 이내로 작성하세요.\n"
        "답변 끝에 [출처: 국가유산포털]을 붙이세요."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # 빠르고 저렴. 품질 더 원하면 "gpt-4o"
        max_tokens=500,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"[참고 자료]\n{context}\n\n[질문]\n{question}",
            },
        ],
    )

    return response.choices[0].message.content


# ─────────────────────────────────────────────────────────
# 의도별 시스템 프롬프트 (Stage 11)
# ─────────────────────────────────────────────────────────
BASE_RULES = (
    "당신은 국가유산청 공식 데이터를 기반으로 안내하는 친근한 AI 해설사입니다.\n"
    "반드시 아래 [참고 자료]에 있는 내용만 근거로 답변하세요.\n"
    "참고 자료에 없는 내용은 \"해당 정보가 없습니다\"라고 답하세요.\n"
    "답변 끝에 [출처: 국가유산포털]을 붙이세요."
)

INTENT_PROMPTS = {
    "explain": BASE_RULES + "\n답변은 친근하지만 정확하게, 4~6문장 이내로 작성하세요.",

    "easy": BASE_RULES + "\n초등학생도 이해할 수 있게 쉬운 어휘로, 3~4문장 이내로 작성하세요.\n전문 용어는 풀어서 설명하세요.",

    "deep": BASE_RULES + "\n역사적 배경·시대 맥락·건축 양식·문화적 의미까지 포함해서 자세히 설명하세요.\n7~10문장 이내.",

    "quiz": (
        BASE_RULES
        + "\n참고 자료의 내용을 바탕으로 객관식 4지선다 퀴즈 1문제를 만들어주세요.\n"
        + "형식: 문제 본문 → ① ② ③ ④ 보기 → 정답 + 간단한 해설.\n"
        + "답변 끝에 [출처: 국가유산포털] 표시."
    ),

    "recommend": (
        BASE_RULES
        + "\n참고 자료에서 관련된 유산 2~3개를 추천하고 각각 한 줄로 소개하세요.\n"
        + "추천 사유(같은 시대/지역/주제)를 명시하세요."
    ),

    "compare": (
        BASE_RULES
        + "\n참고 자료에 있는 두 유산을 비교하세요.\n"
        + "공통점·차이점·각 특징을 명확히 구분해서 표현하세요.\n"
        + "참고 자료에 두 유산 중 하나라도 없으면 \"해당 정보가 없습니다\" 답하세요."
    ),

    "out_of_scope": (
        "당신은 국가유산 전문 AI 해설사입니다.\n"
        "사용자가 국가유산과 무관한 질문을 했습니다.\n"
        "친근하지만 명확하게 \"저는 국가유산 전문 챗봇이에요. 국가유산에 대해 물어봐주세요!\" 라고 답하세요.\n"
        "예시 질문 2개도 함께 안내하세요 (예: '경복궁 알려줘', '조선시대 궁궐 추천')."
    ),
}


# Stage 9: 모르는 유산 처리 — similarity 임계값
# ChromaDB는 L2 distance 기반 (낮을수록 가까움). KoSimCSE 768차원은 분산 큼.
# 실험으로 적정값 찾아야 함 (Exp-310, 311, 312 참고).
# 초기 관대값: 2.0 (거의 차단 안 함, BK 첫 실험용)
NO_ANSWER_THRESHOLD = 999.0  # 임시 비활성화. distance 측정 후 적정값으로 조정

# 디버그: 환경변수 RAG_DEBUG=1 이면 distance 출력
import os
_DEBUG = os.getenv("RAG_DEBUG") == "1"


def answer_with_intent(
    question: str,
    intent: str = "explain",
    k: int = 3,
    no_answer_threshold: float = NO_ANSWER_THRESHOLD,
) -> tuple:
    """
    의도별 시스템 프롬프트로 답변 생성.

    Stage 9: similarity score 기반 모르는 유산 처리.
    검색된 최상위 chunk의 distance가 threshold보다 크면 → "정보 없음".

    Returns:
        (답변 문자열, contexts 리스트)
    """
    # out_of_scope는 검색 안 함 (자료 무관)
    if intent == "out_of_scope":
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=200,
            messages=[
                {"role": "system", "content": INTENT_PROMPTS["out_of_scope"]},
                {"role": "user", "content": question},
            ],
        )
        return response.choices[0].message.content, []

    # Stage 9: 점수 기반 검색
    docs_with_scores = vectorstore.similarity_search_with_score(question, k=k)
    if not docs_with_scores:
        return "해당 국가유산 정보를 찾지 못했어요.", []

    best_score = docs_with_scores[0][1]
    if _DEBUG:
        print(f"  [debug] best_score: {best_score:.3f} / threshold: {no_answer_threshold}")
    if best_score > no_answer_threshold:
        # 검색 결과가 충분히 가깝지 않음 → 환각 방지
        fallback = (
            "해당 국가유산 정보를 찾지 못했어요.\n"
            "혹시 유산명을 다시 확인해주시거나, 다른 유산을 검색해보세요. [출처: 국가유산포털]"
        )
        return fallback, []

    docs = [d for d, _ in docs_with_scores]
    contexts = [doc.page_content for doc in docs]
    context_text = "\n\n---\n\n".join(contexts)

    system_prompt = INTENT_PROMPTS.get(intent, INTENT_PROMPTS["explain"])

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=600,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"[참고 자료]\n{context_text}\n\n[질문]\n{question}",
            },
        ],
    )

    return response.choices[0].message.content, contexts


# 프롬프트 버전별 시스템 프롬프트
SYSTEM_PROMPTS_BY_VERSION = {
    "v1": (
        "당신은 국가유산청 공식 데이터를 기반으로 안내하는 친근한 AI 해설사입니다.\n"
        "반드시 아래 [참고 자료]에 있는 내용만 근거로 답변하세요.\n"
        "참고 자료에 없는 내용은 \"해당 정보가 없습니다\"라고 답하세요.\n"
        "답변은 친근하지만 정확하게, 4~6문장 이내로 작성하세요.\n"
        "답변 끝에 [출처: 국가유산포털]을 붙이세요."
    ),
    "v2": (
        "당신은 국가유산청 공식 데이터를 기반으로 안내하는 AI 해설사입니다.\n"
        "\n"
        "[엄격한 규칙]\n"
        "1. 반드시 아래 [참고 자료]에 있는 사실만 답변에 포함하세요.\n"
        "2. 참고 자료에 없는 내용은 **절대 추측하거나 일반 지식으로 보완하지 마세요**.\n"
        "3. 질문에 대한 정보가 자료에 없으면 \"해당 정보가 없습니다\"라고만 답하세요.\n"
        "4. 자료에 정보가 부족하면 \"이 부분은 자료에 명시되어 있지 않습니다\"라고 명시하세요.\n"
        "5. 답변은 4~6문장 이내, 사실 위주로 간결하게.\n"
        "6. 답변 끝에 [출처: 국가유산포털] 표시.\n"
    ),
}


# ─────────────────────────────────────────────────────────
# Stage Exp-104: 룰베이스 Metadata Filter
# 질문에서 시대/지역/분류 키워드 추출 → ChromaDB where 절
# ─────────────────────────────────────────────────────────
ERA_KEYWORDS = {
    "조선": "조선", "조선시대": "조선", "조선 후기": "조선", "조선 전기": "조선",
    "신라": "신라", "신라시대": "신라",
    "통일신라": "통일신라", "통일 신라": "통일신라",
    "고려": "고려", "고려시대": "고려",
    "백제": "백제", "백제시대": "백제",
    "고구려": "고구려",
    "삼국": "삼국시대", "삼국시대": "삼국시대",
    "근대": "근대", "현대": "현대",
}

CATEGORY_KEYWORDS = {
    "국보": "국보",
    "보물": "보물",
    "사적": "사적",
    "명승": "명승",
    "천연기념물": "천연기념물",
    "민속문화재": "민속문화재", "민속": "민속문화재",
    "등록문화재": "등록문화재",
}

REGION_KEYWORDS = {
    "서울": "서울특별시", "서울특별시": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "광주광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도", "강원도": "강원특별자치도",
    "충북": "충청북도", "충청북도": "충청북도",
    "충남": "충청남도", "충청남도": "충청남도",
    "충청": None,  # 충북/충남 모호 → 필터 안 함
    "전북": "전북특별자치도", "전라북도": "전북특별자치도",
    "전남": "전라남도", "전라남도": "전라남도",
    "전라": None,
    "경북": "경상북도", "경상북도": "경상북도",
    "경남": "경상남도", "경상남도": "경상남도",
    "경상": None,
    "제주": "제주특별자치도", "제주도": "제주특별자치도",
    "경주": None,  # region이 아닌 location → 필터 X (시맨틱 검색에 맡김)
}


def extract_metadata_filter(question: str) -> dict:
    """질문에서 era / category / region 키워드 추출 → ChromaDB where 절.

    여러 metadata 매칭 시 $and 결합. 매칭 없으면 빈 dict.
    값이 None인 키워드는 모호 → 무시.
    """
    conds = []

    for kw, era in ERA_KEYWORDS.items():
        if kw in question and era:
            conds.append({"era": era})
            break  # 첫 매칭만

    for kw, cat in CATEGORY_KEYWORDS.items():
        if kw in question and cat:
            conds.append({"category": cat})
            break

    for kw, region in REGION_KEYWORDS.items():
        if kw in question and region:
            conds.append({"region": region})
            break

    if not conds:
        return {}
    if len(conds) == 1:
        return conds[0]
    return {"$and": conds}


def answer_with_context(
    question: str,
    k: int = 3,
    prompt_version: str = "v1",
    use_metadata_filter: bool = False,
) -> tuple:
    """
    answer()와 동일하지만 검색된 context도 함께 반환.
    LLM-as-judge 평가용.

    Args:
        question: 사용자 질문
        k: 검색할 chunk 수
        prompt_version: "v1" (기본) | "v2" (환각 방지 강화)
        use_metadata_filter: True 시 룰베이스 메타 필터 적용 (Exp-104)

    Returns:
        (답변 문자열, context chunk 리스트)
    """
    where = extract_metadata_filter(question) if use_metadata_filter else {}
    if where:
        docs = vectorstore.similarity_search(question, k=k, filter=where)
        # 필터 결과 없으면 필터 해제 (fallback)
        if not docs:
            docs = vectorstore.similarity_search(question, k=k)
    else:
        docs = vectorstore.similarity_search(question, k=k)

    if not docs:
        return "해당 국가유산 정보를 찾지 못했어요.", []

    contexts = [doc.page_content for doc in docs]
    context_text = "\n\n---\n\n".join(contexts)

    system_prompt = SYSTEM_PROMPTS_BY_VERSION.get(
        prompt_version, SYSTEM_PROMPTS_BY_VERSION["v1"]
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=500,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"[참고 자료]\n{context_text}\n\n[질문]\n{question}",
            },
        ],
    )

    return response.choices[0].message.content, contexts


# ─────────────────────────────────────────────────────────
# 4. 테스트 실행
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_questions = [
        "숭례문이 어디에있어?",
        "경복궁 쉽게 설명해줘",
        "조선시대 궁궐 추천해줘",
        "불국사는 어느 시대에 만들어졌어?",
        "에펠탑 알려줘",  # 데이터에 없음 → 모른다고 답해야 함
    ]

    for q in test_questions:
        print(f"\n{'=' * 60}")
        print(f"질문: {q}")
        result = answer(q)
        print(f"\n답변: {result}")
