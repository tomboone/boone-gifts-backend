from datetime import datetime

from pydantic import BaseModel, model_validator


class ConnectionCreate(BaseModel):
    user_id: int | None = None
    email: str | None = None

    @model_validator(mode="after")
    def require_user_id_or_email(self) -> "ConnectionCreate":
        if self.user_id is None and self.email is None:
            raise ValueError("Either user_id or email is required.")
        return self


class ConnectionUserRead(BaseModel):
    id: int
    name: str
    email: str

    model_config = {"from_attributes": True}


class ConnectionRead(BaseModel):
    id: int
    status: str
    user: ConnectionUserRead
    created_at: datetime
    accepted_at: datetime | None

    model_config = {"from_attributes": True}
