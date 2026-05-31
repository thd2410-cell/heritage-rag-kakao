import re

UNWANTED_CJK_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\u3040-\u30FF]+")
EMPTY_PARENS_RE = re.compile(r"\(\s*\)")
SPACES_RE = re.compile(r"[ \t]{2,}")


def has_unwanted_cjk(text: str) -> bool:
    return bool(UNWANTED_CJK_RE.search(text))


def remove_unwanted_cjk(text: str) -> str:
    cleaned = UNWANTED_CJK_RE.sub("", text)
    cleaned = EMPTY_PARENS_RE.sub("", cleaned)
    cleaned = SPACES_RE.sub(" ", cleaned)
    return cleaned.strip()
