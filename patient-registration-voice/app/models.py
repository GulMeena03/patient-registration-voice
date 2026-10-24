import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Date, DateTime, Index, text
from .database import Base


def _now():
    return datetime.now(timezone.utc)


class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    sex = Column(String(20), nullable=False)
    phone_number = Column(String(20), nullable=False)
    email = Column(String(254))
    address_line_1 = Column(String(255), nullable=False)
    address_line_2 = Column(String(255))
    city = Column(String(100), nullable=False)
    state = Column(String(2), nullable=False)
    zip_code = Column(String(10), nullable=False)
    insurance_provider = Column(String(255))
    insurance_member_id = Column(String(100))
    preferred_language = Column(String(50), nullable=False, default="English")
    emergency_contact_name = Column(String(255))
    emergency_contact_phone = Column(String(20))
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)  # soft delete

    __table_args__ = (
        # Unique phone among ACTIVE patients only (partial index; SQLite + Postgres both support it)
        Index(
            "uq_patients_active_phone",
            "phone_number",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_patients_last_name", "last_name"),
    )
