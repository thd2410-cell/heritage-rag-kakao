from app.schemas.route import RouteRecommendationInput
from app.services.route.map_provider import MapProvider, MockMapProvider


class RoutePlanner:
    def __init__(self, map_provider: MapProvider | None = None):
        self.map_provider = map_provider or MockMapProvider()

    def plan(self, entity_id: str | None, route_input: RouteRecommendationInput) -> dict:
        if route_input.audience == "elderly" or route_input.mobility.minimize_walking:
            stops = [
                ("광화문", None, "출발 지점입니다.", "이동 전 휴식 가능 지점을 확인하세요."),
                ("근정전", "geunjeongjeon", "경복궁의 중심 건물입니다.", "계단과 혼잡 구간을 주의하세요."),
                ("경회루", "gyeonghoeru", "연회와 외국 사신 접대에 사용된 누각입니다.", "주변에서 짧게 쉬어가세요."),
                ("종료", None, "무리하지 않고 관람을 마칩니다.", "추가 이동은 현장 안내를 확인하세요."),
            ]
            title = "경복궁 고령자용 1시간 코스"
        else:
            stops = [
                ("광화문", None, "출발 지점입니다.", ""),
                ("근정전", "geunjeongjeon", "경복궁의 중심 건물입니다.", ""),
                ("경회루", "gyeonghoeru", "연회와 외국 사신 접대에 사용된 누각입니다.", ""),
                ("향원정", "hyangwonjeong", "후원 영역의 정자입니다.", ""),
            ]
            title = "경복궁 핵심 1시간 코스"
        stay = self.map_provider.estimate_minutes(len(stops), route_input.duration_minutes)
        return {
            "route_title": title,
            "estimated_duration_minutes": route_input.duration_minutes,
            "stops": [
                {"order": i + 1, "heritage_id": hid, "name": name, "description": desc, "estimated_stay_minutes": stay, "accessibility_note": note}
                for i, (name, hid, desc, note) in enumerate(stops)
            ],
            "route_reason": "LLM이 임의 계산하지 않고 MVP RoutePlanner 규칙과 관계 데이터를 기준으로 구성한 코스입니다.",
            "warnings": ["현장 공사, 행사, 혼잡도에 따라 실제 동선은 달라질 수 있습니다."],
        }
