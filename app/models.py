from datetime import UTC, date, datetime
from enum import Enum

from sqlalchemy import Date, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class GameStatus(str, Enum):
    BACKLOG = "backlog"
    PLAYING = "playing"
    COMPLETED = "completed"
    DROPPED = "dropped"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    bio: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="Tracking every quest, cozy run, and late-night backlog impulse.",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    game_logs: Mapped[list["UserGame"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    genre: Mapped[str | None] = mapped_column(String(100), nullable=True)
    steam_app_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    steam_icon_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    steam_logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    user_logs: Mapped[list["UserGame"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )


class UserGame(Base):
    __tablename__ = "user_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    status: Mapped[GameStatus] = mapped_column(SqlEnum(GameStatus), nullable=False)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review: Mapped[str | None] = mapped_column(Text, nullable=True)
    played_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    import_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    steam_playtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="game_logs")
    game: Mapped[Game] = relationship(back_populates="user_logs")
