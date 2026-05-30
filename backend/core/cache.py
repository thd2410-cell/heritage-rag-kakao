"""간단한 인메모리 LRU 캐시.

같은 유산을 같은 언어로 재조회할 때 LLM 호출(비용·지연·레이트리밋)을 피하기
위한 용도. 프로세스 메모리에만 저장되며 서버 재시작 시 비워진다.

TTL(초)을 두어 오래된 항목은 자동 만료시킬 수 있다.
시간 함수를 주입 가능하게 하여(스크립트 환경에서 time 제약 회피) 테스트가 쉽다.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional


class SimpleCache:
    """스레드 안전한 LRU + TTL 캐시."""

    def __init__(
        self,
        maxsize: int = 256,
        ttl: Optional[float] = None,
        *,
        time_func: Callable[[], float] = time.time,
    ):
        self.maxsize = maxsize
        self.ttl = ttl
        self._time = time_func
        self._store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """캐시 값을 반환한다. 없거나 만료됐으면 None."""
        with self._lock:
            item = self._store.get(key)
            if item is None:
                self.misses += 1
                return None
            ts, value = item
            if self.ttl is not None and (self._time() - ts) > self.ttl:
                # 만료
                del self._store[key]
                self.misses += 1
                return None
            # 최근 사용으로 갱신 (LRU)
            self._store.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (self._time(), value)
            # 용량 초과 시 가장 오래된 항목 제거
            while len(self._store) > self.maxsize:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "size": len(self._store),
                "maxsize": self.maxsize,
                "ttl": self.ttl,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
            }


if __name__ == "__main__":
    # 주입형 시계로 TTL/LRU 동작 검증 (스크립트 환경 time 제약 회피)
    clock = {"t": 0.0}
    c = SimpleCache(maxsize=2, ttl=10, time_func=lambda: clock["t"])

    c.set("a", 1)
    assert c.get("a") == 1, "기본 get/set"
    print("기본 get/set OK")

    # TTL 만료
    clock["t"] = 11.0
    assert c.get("a") is None, "TTL 만료"
    print("TTL 만료 OK")

    # LRU 축출 (maxsize=2)
    clock["t"] = 12.0
    c.set("x", "X"); c.set("y", "Y")
    c.get("x")                 # x 최근 사용
    c.set("z", "Z")            # 용량 초과 -> 가장 오래된 y 축출
    assert c.get("y") is None, "LRU 축출 대상은 y"
    assert c.get("x") == "X" and c.get("z") == "Z", "x,z 유지"
    print("LRU 축출 OK")
    print("stats:", c.stats())
