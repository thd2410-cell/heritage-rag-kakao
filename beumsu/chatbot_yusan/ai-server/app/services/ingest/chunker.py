class DocumentChunker:
    def chunk(self, content: str, max_chars: int = 900) -> list[str]:
        return [content[i : i + max_chars] for i in range(0, len(content), max_chars)] or [""]
