"""용어 사전 레이어 (파이프라인 3단계).

국가유산 해설 원문에는 '홍예문', '우진각지붕', '다포 양식' 같은 전문 용어가
많다. 이 모듈은 다음을 담당한다.

  1. 사전 매칭   : term_dictionary.json 에 정의된 용어가 원문에 있는지 탐지
  2. 자동 추출   : `단어(한자)` 패턴을 정규식으로 찾아 신규 용어 후보 발굴
  3. 컨텍스트 생성: 탐지된 용어 정의를 LLM 시스템 프롬프트용 [용어 정의] 블록으로 조립

LLM 호출 시 이 정의를 주입하여 용어의 의미가 왜곡되지 않도록 한다.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# 기본 사전 경로: backend/data/term_dictionary.json
_DEFAULT_DICT_PATH = Path(__file__).resolve().parent.parent / "data" / "term_dictionary.json"

# `단어(한자)` 패턴. 괄호 바로 앞의 '연속된 한글 한 덩어리'만 용어로 잡는다.
#   "사리분신(舍利分身)"        -> ("사리분신", "舍利分身")
#   "...받침돌인 귀부(龜趺)"     -> ("귀부", "龜趺")   (앞 문장은 공백으로 끊겨 제외됨)
# 공백을 포함하지 않으므로 앞 문장 전체를 삼키지 않는다. 다중 단어 용어는
# 시드 사전이 담당하고, 자동 추출은 단일 토큰 신규 후보 발굴에 집중한다.
_HANJA_TERM_PATTERN = re.compile(
    r"([가-힣]+)\s*\(\s*([一-鿿]+)\s*\)"
)


@dataclass
class ExtractedTerm:
    """원문에서 자동 추출한 `단어(한자)` 후보."""

    korean: str
    hanja: str


class TermDictionary:
    """용어 사전 로드 및 탐지/조립 기능을 제공한다."""

    def __init__(self, dict_path: Optional[Path | str] = None):
        self.dict_path = Path(dict_path) if dict_path else _DEFAULT_DICT_PATH
        self._terms: dict[str, str] = self._load()
        # 긴 용어 우선 매칭을 위해 길이 내림차순 정렬해 둔 키 목록
        self._keys_by_len: list[str] = sorted(
            self._terms, key=len, reverse=True
        )

    def _load(self) -> dict[str, str]:
        if not self.dict_path.exists():
            return {}
        with open(self.dict_path, encoding="utf-8") as f:
            return json.load(f)

    # ── 조회 ─────────────────────────────────────────────
    def __len__(self) -> int:
        return len(self._terms)

    def __contains__(self, term: str) -> bool:
        return term in self._terms

    def get(self, term: str) -> Optional[str]:
        return self._terms.get(term)

    # ── 탐지 ─────────────────────────────────────────────
    def detect_terms(self, content: str) -> dict[str, str]:
        """원문에서 사전에 정의된 용어를 탐지해 {용어: 정의} 로 반환한다.

        더 긴 용어가 매칭되면, 그 안에 포함된 짧은 용어(예: '다포 양식'에
        포함된 '다포')는 중복으로 보고하지 않는다. 본문 등장 순서를 유지한다.
        """
        if not content:
            return {}

        # 1) 사전에 있고 본문에 등장하는 용어 수집
        present = [k for k in self._keys_by_len if k in content]

        # 2) 다른(더 긴) 매칭 용어의 부분 문자열인 용어는 제거
        filtered: list[str] = []
        for term in present:
            if any(term != other and term in other for other in present):
                continue
            filtered.append(term)

        # 3) 본문 등장 위치 순으로 정렬
        filtered.sort(key=lambda t: content.find(t))
        return {t: self._terms[t] for t in filtered}

    # ── 자동 추출 ────────────────────────────────────────
    def extract_hanja_terms(self, content: str) -> list[ExtractedTerm]:
        """`단어(한자)` 패턴을 정규식으로 추출한다. (중복 제거, 등장 순서 유지)"""
        seen: set[str] = set()
        result: list[ExtractedTerm] = []
        for m in _HANJA_TERM_PATTERN.finditer(content or ""):
            korean = m.group(1).strip()
            hanja = m.group(2).strip()
            if korean in seen:
                continue
            seen.add(korean)
            result.append(ExtractedTerm(korean=korean, hanja=hanja))
        return result

    def unknown_hanja_terms(self, content: str) -> list[ExtractedTerm]:
        """추출된 `단어(한자)` 중 아직 사전에 없는 신규 후보만 반환한다.

        용어 사전 자동 확장(Phase 2)의 입력으로 사용할 수 있다.
        """
        return [t for t in self.extract_hanja_terms(content) if t.korean not in self._terms]

    def context_for(self, term: str, content: str, window: int = 80) -> str:
        """원문에서 해당 용어가 등장한 주변 문맥을 잘라 반환한다. (정의 생성용)"""
        idx = content.find(term)
        if idx < 0:
            return content[: window * 2]
        start = max(0, idx - window)
        end = min(len(content), idx + len(term) + window)
        return content[start:end]

    # ── 사전 확장(쓰기) ──────────────────────────────────
    def add_term(self, term: str, definition: str, *, persist: bool = True) -> bool:
        """사전에 용어를 추가한다. 이미 있으면 False, 추가하면 True.

        persist=True 면 JSON 파일에 안전하게(임시파일 후 교체) 저장한다.
        """
        term = (term or "").strip()
        definition = (definition or "").strip()
        if not term or not definition or term in self._terms:
            return False
        self._terms[term] = definition
        # 길이 내림차순 정렬 키 목록 갱신
        self._keys_by_len = sorted(self._terms, key=len, reverse=True)
        if persist:
            self.save()
        return True

    def save(self) -> None:
        """현재 사전을 JSON 파일로 안전하게 저장한다 (임시파일 → os.replace)."""
        self.dict_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.dict_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._terms, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.dict_path)

    # ── 컨텍스트 조립 ────────────────────────────────────
    def build_term_context(self, content: str) -> str:
        """탐지된 용어 정의를 LLM 프롬프트용 [용어 정의] 블록 문자열로 만든다.

        탐지된 용어가 없으면 빈 문자열을 반환한다. 반환 형식 예::

            - 홍예문: 반원 형태의 아치형 문...
            - 우진각지붕: 지붕의 네 면이 모두...
        """
        detected = self.detect_terms(content)
        if not detected:
            return ""
        lines = [f"- {term}: {definition}" for term, definition in detected.items()]
        return "\n".join(lines)


# 모듈 수준 기본 인스턴스 (편의용)
_default_dictionary: Optional[TermDictionary] = None


def get_default_dictionary() -> TermDictionary:
    """싱글톤 기본 사전 인스턴스를 반환한다."""
    global _default_dictionary
    if _default_dictionary is None:
        _default_dictionary = TermDictionary()
    return _default_dictionary


def detect_terms(content: str) -> dict[str, str]:
    """기본 사전으로 용어를 탐지하는 모듈 수준 편의 함수."""
    return get_default_dictionary().detect_terms(content)


def build_term_context(content: str) -> str:
    """기본 사전으로 [용어 정의] 블록을 만드는 모듈 수준 편의 함수."""
    return get_default_dictionary().build_term_context(content)


if __name__ == "__main__":
    # 숭례문 해설 원문(상세 API content)으로 용어 레이어 테스트
    sample = (
        "조선시대 한양도성의 정문으로 남쪽에 있다고 해서 남대문이라고도 불렀다. "
        "이 문은 돌을 높이 쌓아 만든 석축 가운데에 무지개 모양의 홍예문을 두고, "
        "그 위에 앞면 5칸·옆면 2칸 크기로 지은 누각형 2층 건물이다. "
        "지붕은 앞면에서 볼 때 사다리꼴 형태를 하고 있는데, 이러한 지붕을 우진각지붕이라 한다. "
        "지붕 처마를 받치기 위해 기둥 위부분에 장식하여 짠 구조가 기둥 위뿐만 아니라 "
        "기둥 사이에도 있는 다포 양식으로, 그 형태가 곡이 심하지 않다. "
        "2008년 숭례문 방화 사건(崇禮門放火事件)은 방화로 타 무너진 사건이다."
    )

    d = TermDictionary()
    print(f"[사전 로드] 총 {len(d)}개 용어\n")

    print("=" * 60)
    print("[사전 매칭] 본문에서 탐지된 용어")
    print("=" * 60)
    for term, definition in d.detect_terms(sample).items():
        print(f"- {term}: {definition[:40]}...")

    print()
    print("=" * 60)
    print("[자동 추출] `단어(한자)` 패턴")
    print("=" * 60)
    for t in d.extract_hanja_terms(sample):
        in_dict = "사전 O" if t.korean in d else "신규 후보"
        print(f"- {t.korean} ({t.hanja})  [{in_dict}]")

    print()
    print("=" * 60)
    print("[LLM 주입용] build_term_context() 결과")
    print("=" * 60)
    print(d.build_term_context(sample))
