from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas


class DuplicatePhoneError(Exception):
    pass


def _active(db: Session):
    return db.query(models.Patient).filter(models.Patient.deleted_at.is_(None))


def get_patient(db: Session, patient_id: str) -> Optional[models.Patient]:
    return _active(db).filter(models.Patient.patient_id == patient_id).first()


def get_patient_by_phone(db: Session, phone: str) -> Optional[models.Patient]:
    return _active(db).filter(models.Patient.phone_number == phone).first()


def list_patients(db: Session, last_name: Optional[str] = None,
                  date_of_birth: Optional[date] = None,
                  phone_number: Optional[str] = None) -> List[models.Patient]:
    q = _active(db)
    if last_name:
        q = q.filter(models.Patient.last_name.ilike(f"%{last_name}%"))
    if date_of_birth:
        q = q.filter(models.Patient.date_of_birth == date_of_birth)
    if phone_number:
        q = q.filter(models.Patient.phone_number == phone_number)
    return q.order_by(models.Patient.created_at.desc()).all()


def create_patient(db: Session, data: schemas.PatientCreate) -> models.Patient:
    patient = models.Patient(**data.model_dump())
    db.add(patient)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicatePhoneError()
    db.refresh(patient)
    return patient


def update_patient(db: Session, patient_id: str, data: schemas.PatientUpdate) -> Optional[models.Patient]:
    patient = get_patient(db, patient_id)
    if not patient:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is None and key in schemas.REQUIRED_FIELDS:
            continue  # required fields can't be cleared
        setattr(patient, key, value)
    patient.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicatePhoneError()
    db.refresh(patient)
    return patient


def soft_delete_patient(db: Session, patient_id: str) -> bool:
    patient = get_patient(db, patient_id)
    if not patient:
        return False
    patient.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return True
