from datetime import datetime
from sqlalchemy import BigInteger, Column, String, Boolean, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class GroupSetting(Base):
    __tablename__ = "group_settings"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    captcha_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    captcha_timeout_sec: Mapped[int] = mapped_column(Integer, default=60)

    block_all_links: Mapped[bool] = mapped_column(Boolean, default=True)
    block_telegram_invites: Mapped[bool] = mapped_column(Boolean, default=True)

    anti_flood_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    anti_flood_limit: Mapped[int] = mapped_column(Integer, default=5)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)