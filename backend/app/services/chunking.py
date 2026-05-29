def chunk_text(text: str, min_chars: int = 300, max_chars: int = 800) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in text.replace("\r\n", "\n").split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + 2 + len(para) <= max_chars:
            current += "\n\n" + para
        else:
            if len(current) < min_chars and len(para) <= max_chars:
                current += "\n\n" + para
            else:
                chunks.append(current[:max_chars].strip())
                current = para
    if current:
        if len(current) > max_chars:
            chunks.extend(current[i:i + max_chars].strip() for i in range(0, len(current), max_chars))
        else:
            chunks.append(current.strip())
    return [c for c in chunks if c]
