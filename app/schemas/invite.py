from datetime import datetime

from pydantic import BaseModel


class InviteCreate(BaseModel):
    email: str
    role: str = "member"
    expires_in_days: int = 7


class InviteRead(BaseModel):
    id: int
    token: str
    email: str
    role: str
    expires_at: datetime
    used_at: datetime | None
    invited_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
