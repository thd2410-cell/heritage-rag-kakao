import re


PATTERNS = [
    r"ignore\s+previous\s+instructions",
    r"system\s+prompt",
    r"출처\s*무시",
    r"근거\s*없이",
    r"프롬프트.*보여",
    r"위\s*지시.*무시",
]


def detect_prompt_injection(text: str) -> list[str]:
    return [pattern for pattern in PATTERNS if re.search(pattern, text, re.I)]
