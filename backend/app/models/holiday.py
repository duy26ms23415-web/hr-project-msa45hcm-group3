from datetime import date, datetime
from sqlalchemy import BigInteger, String, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Holiday(Base):
    __tablename__ = "hr_holidays"

    holiday_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    holiday_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    holiday_name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hr_user_accounts.user_account_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    creator: Mapped["UserAccount"] = relationship("UserAccount")
