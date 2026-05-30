from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    supports_structured_output: bool = False

    @abstractmethod
    def generate(self, messages: list[dict], response_schema: Any = None, temperature: float = 0.2) -> str:
        raise NotImplementedError

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0


class DummyProvider(LLMProvider):
    def generate(self, messages: list[dict], response_schema: Any = None, temperature: float = 0.2) -> str:
        evidence = ""
        for message in messages:
            if message.get("role") == "system" and "<evidence>" in message.get("content", ""):
                evidence = message["content"].rsplit("<evidence>", 1)[-1].split("</evidence>", 1)[0].strip()
        if not evidence:
            return "확인된 자료에서는 해당 내용을 찾기 어렵습니다."
        first_line = evidence.split("\n", 1)[0]
        return first_line.rsplit("content=", 1)[-1].strip()


class LocalMockProvider(DummyProvider):
    pass


class OpenAIProvider(LLMProvider):
    supports_structured_output = True

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini"):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The openai package is required when LLM_PROVIDER=openai") from exc
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, messages: list[dict], response_schema: Any = None, temperature: float = 0.2) -> str:
        instructions = "\n\n".join(
            str(message.get("content", "")) for message in messages if message.get("role") in {"system", "developer"}
        )
        input_messages = [
            {"role": message.get("role", "user"), "content": str(message.get("content", ""))}
            for message in messages
            if message.get("role") not in {"system", "developer"}
        ]
        response_kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            "input": input_messages,
            "temperature": temperature,
        }
        if response_schema:
            response_kwargs["text"] = {"format": response_schema}
        response = self.client.responses.create(**response_kwargs)
        text = getattr(response, "output_text", None)
        if text:
            return text.strip()
        output = getattr(response, "output", []) or []
        parts: list[str] = []
        for item in output:
            for content in getattr(item, "content", []) or []:
                value = getattr(content, "text", None)
                if value:
                    parts.append(value)
        return "\n".join(parts).strip()


def build_llm_provider(provider_name: str, api_key: str = "", model: str = "gpt-4.1-mini") -> LLMProvider:
    provider_name = (provider_name or "dummy").lower()
    if provider_name == "openai":
        return OpenAIProvider(api_key=api_key, model=model)
    if provider_name in {"local_mock", "mock"}:
        return LocalMockProvider()
    return DummyProvider()
