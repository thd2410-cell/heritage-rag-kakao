from app.services.cache.memory_cache import MemoryCache


class RedisCache(MemoryCache):
    """Redis-compatible placeholder. Falls back to memory in the MVP test environment."""

    pass
