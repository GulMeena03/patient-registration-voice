from datetime import date

from . import crud, schemas
from .database import Base, SessionLocal, engine
from .models import Patient

SEED = [
    dict(first_name="Jane", last_name="Doe", date_of_birth=date(1985, 3, 15), sex="Female",
         phone_number="+12175550142", email="jane.doe@example.com", address_line_1="123 Main St",
         address_line_2="Apt 4B", city="Springfield", state="IL", zip_code="62704",
         insurance_provider="Blue Cross", insurance_member_id="BC123456", preferred_language="English",
         emergency_contact_name="John Doe", emergency_contact_phone="+12175550199"),
    dict(first_name="Carlos", last_name="Ramirez", date_of_birth=date(1990, 7, 22), sex="Male",
         phone_number="+15125550187", email="carlos.r@example.com", address_line_1="456 Oak Ave",
         city="Austin", state="TX", zip_code="78701", preferred_language="Spanish"),
]


def seed() -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Patient).count() > 0:
            return 0
        for row in SEED:
            crud.create_patient(db, schemas.PatientCreate(**row))
        return len(SEED)
    finally:
        db.close()


if __name__ == "__main__":
    print(f"Seeded {seed()} patients.")
