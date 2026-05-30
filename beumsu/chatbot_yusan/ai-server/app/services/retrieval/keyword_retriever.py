from app.services.translation.glossary import normalize_key


class KeywordScorer:
    def score(self, query_terms: list[str], title: str, content: str) -> float:
        haystack = normalize_key(title + " " + content)
        if not query_terms:
            return 0.0
        hits = sum(1 for term in query_terms if normalize_key(term) and normalize_key(term) in haystack)
        return min(1.0, hits / max(1, len(query_terms)))
