class MapProvider:
    def estimate_minutes(self, stop_count: int, duration_minutes: int) -> int:
        return max(5, duration_minutes // max(1, stop_count))


class MockMapProvider(MapProvider):
    pass
