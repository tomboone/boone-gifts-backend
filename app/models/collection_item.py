from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (
        UniqueConstraint(
            "collection_id", "list_id", name="uq_collection_items_collection_list"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"))
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
