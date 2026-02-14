from decimal import Decimal

from pydantic import BaseModel


class GiftCreate(BaseModel):
    name: str
    description: str | None = None
    url: str | None = None
    price: Decimal | None = None


class GiftUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    url: str | None = None
    price: Decimal | None = None
