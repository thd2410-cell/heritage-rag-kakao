import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from app.db.session import SessionLocal, get_db
from app.models.heritage import ChatLog
from app.schemas.kakao import KakaoSkillRequest
from app.services.answer_builder import build_personalized_answer, wants_travel_visit
from app.services.conversation import resolve_contextual_question
from app.services.domain import OUT_OF_DOMAIN_MESSAGE, is_heritage_domain
from app.services.guardrails import check_guardrail
from app.services.retrieval import search_chunks_fast
from app.services.text_cleaning import remove_unwanted_cjk

router = APIRouter(prefix="/api/kakao", tags=["kakao"])
logger = logging.getLogger(__name__)

QUICK_REPLIES = [
    {"label": "쉽게 설명", "action": "message", "messageText": "쉽게 설명해줘"},
    {"label": "심화 설명", "action": "message", "messageText": "심화 설명해줘"},
    {"label": "위치/근처", "action": "message", "messageText": "근처에 뭐 있어?"},
    {"label": "관련 유산", "action": "message", "messageText": "관련 유산 추천해줘"},
]


def kakao_text_response(text: str) -> dict:
    safe_text = remove_unwanted_cjk(text)
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": safe_text[:1000]}}],
            "quickReplies": QUICK_REPLIES,
        },
    }


def kakao_callback_wait_response() -> dict:
    return {
        "version": "2.0",
        "useCallback": True,
        "data": {"text": "국가유산 자료를 확인하고 있어요. 잠시만 기다려 주세요."},
    }


def build_kakao_answer(db: Session, utterance: str, user_key: str | None) -> tuple[str, list[dict]]:
    blocked = check_guardrail(utterance)
    if blocked:
        db.add(ChatLog(user_key=user_key, utterance=utterance, answer=blocked, sources=[]))
        db.commit()
        return blocked, []

    resolution = resolve_contextual_question(db, utterance, user_key, fast=True)
    if resolution.needs_clarification:
        answer = resolution.clarification or "어떤 국가유산에 대한 질문인지 알려주세요."
        db.add(ChatLog(user_key=user_key, utterance=utterance, answer=answer, sources=[]))
        db.commit()
        return answer, []

    contexts = search_chunks_fast(
        db,
        resolution.question,
        limit=3,
        include_nearby=wants_travel_visit(resolution.question),
    )
    if not is_heritage_domain(resolution.question) and not contexts:
        answer = OUT_OF_DOMAIN_MESSAGE
        db.add(ChatLog(user_key=user_key, utterance=utterance, answer=answer, sources=[]))
        db.commit()
        return answer, []

    answer = remove_unwanted_cjk(build_personalized_answer(resolution.question, contexts))
    db.add(ChatLog(user_key=user_key, utterance=utterance, answer=answer, sources=contexts))
    db.commit()
    return answer, contexts


async def send_callback_answer(callback_url: str, utterance: str, user_key: str | None) -> None:
    try:
        with SessionLocal() as db:
            answer, _ = build_kakao_answer(db, utterance, user_key)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(callback_url, json=kakao_text_response(answer))
            logger.info("kakao callback post status=%s body=%s", response.status_code, response.text[:300])
    except Exception:
        logger.exception("kakao callback post failed")


@router.post("/skill")
def kakao_skill(payload: KakaoSkillRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    utterance = payload.utterance.strip()
    logger.info("kakao skill request utterance=%r user_key=%r callback=%s", utterance, payload.user_key, bool(payload.callback_url))

    if payload.callback_url:
        background_tasks.add_task(send_callback_answer, payload.callback_url, utterance, payload.user_key)
        return kakao_callback_wait_response()

    answer, _ = build_kakao_answer(db, utterance, payload.user_key)
    return kakao_text_response(answer)
