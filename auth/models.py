"""
Auth models — User table with password hash.
Extends the existing SQLAlchemy Base from ComfyUI's app.database.models.
"""
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base


class User(Base):
    __tablename__ = "auth_users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True
    )
    username: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    password_hash: Mapped[str] = mapped_column(
        String(256), nullable=False
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=datetime.utcnow
    )
    last_login: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=True, default=None
    )

    __table_args__ = (
        Index("ix_auth_users_username", "username"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
