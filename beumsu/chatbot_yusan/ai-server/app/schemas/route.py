from pydantic import BaseModel, Field


class Mobility(BaseModel):
    avoid_stairs: bool = False
    minimize_walking: bool = False


class RouteRecommendationInput(BaseModel):
    start: str = "광화문"
    duration_minutes: int = 60
    audience: str = "general"
    interests: list[str] = Field(default_factory=list)
    mobility: Mobility = Field(default_factory=Mobility)
