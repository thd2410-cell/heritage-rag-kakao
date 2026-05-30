from app.db.repository import HeritageRepository


class GraphRetriever:
    def __init__(self, repo: HeritageRepository):
        self.repo = repo

    def expand(self, entity_ids: list[str], limit: int = 3) -> dict[str, float]:
        expanded: dict[str, float] = {}
        for entity_id in entity_ids:
            for related in self.repo.related_entity_ids(entity_id)[:limit]:
                expanded[related] = max(expanded.get(related, 0.0), 0.6)
        return expanded
