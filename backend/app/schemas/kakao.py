from typing import Any
from pydantic import BaseModel, Field


class KakaoSkillRequest(BaseModel):
    userRequest: dict[str, Any] = Field(default_factory=dict)

    @property
    def utterance(self) -> str:
        return str(self.userRequest.get("utterance") or "")

    @property
    def user_key(self) -> str | None:
        user = self.userRequest.get("user") or {}
        return (
            user.get("id")
            or user.get("botUserKey")
            or user.get("plusfriendUserKey")
            or self.userRequest.get("botUserKey")
            or self.userRequest.get("plusfriendUserKey")
        )
