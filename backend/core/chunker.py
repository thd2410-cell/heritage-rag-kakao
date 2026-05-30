"""해설 원문 청크 분할 (RAG용).

문단(줄바꿈) 기준으로 1차 분할하고, 한 문단이 최대 길이를 넘으면 문장 단위로
다시 나눠 누적한다. 각 청크는 최대 max_len(기본 300자)을 넘지 않도록 한다.
"""

from __future__ import annotations

import re

DEFAULT_MAX_LEN = 300

# 문장 경계: 한국어 종결('다.', '요.') 및 일반 종결부호 뒤의 공백/줄바꿈
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+")


def _split_sentences(paragraph: str) -> list[str]:
    """문단을 문장 리스트로 나눈다."""
    parts = _SENTENCE_SPLIT.split(paragraph)
    return [p.strip() for p in parts if p.strip()]


def _pack_sentences(sentences: list[str], max_len: int) -> list[str]:
    """문장들을 max_len 이내로 누적하여 청크로 묶는다."""
    chunks: list[str] = []
    buf = ""
    for sent in sentences:
        # 한 문장이 자체로 너무 길면 글자 수로 강제 분할
        if len(sent) > max_len:
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(sent), max_len):
                chunks.append(sent[i : i + max_len])
            continue
        # 누적 시 초과하면 flush 후 새 버퍼 시작
        if buf and len(buf) + 1 + len(sent) > max_len:
            chunks.append(buf)
            buf = sent
        else:
            buf = f"{buf} {sent}".strip() if buf else sent
    if buf:
        chunks.append(buf)
    return chunks


def chunk_text(text: str, *, max_len: int = DEFAULT_MAX_LEN) -> list[str]:
    """원문을 문단→문장 기준으로 청크 분할한다.

    Args:
        text: 해설 원문.
        max_len: 청크 최대 글자 수 (기본 300).

    Returns:
        청크 문자열 리스트 (공백 청크 제외).
    """
    if not text or not text.strip():
        return []

    chunks: list[str] = []
    # 1차: 문단(줄바꿈) 기준
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    for para in paragraphs:
        if len(para) <= max_len:
            chunks.append(para)
        else:
            # 2차: 문장 단위로 누적
            chunks.extend(_pack_sentences(_split_sentences(para), max_len))
    return chunks


if __name__ == "__main__":
    sample = (
        "조선시대 한양도성의 정문으로 남쪽에 있다고 해서 남대문이라고도 불렀다. "
        "현재 서울에 남아 있는 목조 건물 중 가장 오래된 것으로 태조 5년(1396)에 짓기 시작하여 "
        "태조 7년(1398)에 완성하였다. 이후 2008년 2월 10일 숭례문 방화 화재로 누각 2층 지붕이 "
        "붕괴되고 1층 지붕도 일부 소실되는 등 큰 피해를 입었으며, 5년 2개월에 걸친 복원공사 끝에 "
        "2013년 5월 4일 준공되어 일반에 공개되고 있다.\n"
        "이 문은 돌을 높이 쌓아 만든 석축 가운데에 무지개 모양의 홍예문을 두고, 그 위에 "
        "앞면 5칸·옆면 2칸 크기로 지은 누각형 2층 건물이다. 지붕은 우진각지붕이며 다포 양식이다."
    )
    chunks = chunk_text(sample, max_len=300)
    print(f"청크 수: {len(chunks)}")
    for i, c in enumerate(chunks, 1):
        print(f"[{i}] ({len(c)}자) {c}")
