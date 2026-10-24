import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from . import crud, schemas
from .database import Base, engine, get_db
from .vapi_webhook import router as vapi_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if os.getenv("SEED_ON_START", "").lower() == "true":
        from .seed import seed
        seed()
    yield


app = FastAPI(title="Patient Registration API", version="1.0.0", lifespan=lifespan,
              description="REST API + Vapi tool webhook for voice-based patient registration.")
app.include_router(vapi_router)


def envelope(data=None, error=None):
    return {"data": data, "error": error}


@app.exception_handler(HTTPException)
async def http_exc(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content=envelope(error={"message": exc.detail}))


@app.exception_handler(RequestValidationError)
async def validation_exc(_: Request, exc: RequestValidationError):
    errs = [{"field": ".".join(str(x) for x in e["loc"][1:]) or "body",
             "message": e["msg"].replace("Value error, ", "")} for e in exc.errors()]
    return JSONResponse(status_code=422, content=envelope(error={"message": "Validation failed", "details": errs}))


def _out(p) -> dict:
    return schemas.PatientOut.model_validate(p).model_dump(mode="json")


@app.get("/patients")
def list_patients(last_name: Optional[str] = Query(None), date_of_birth: Optional[date] = Query(None),
                  phone_number: Optional[str] = Query(None), db: Session = Depends(get_db)):
    phone = None
    if phone_number:
        try:
            phone = schemas.normalize_phone(phone_number)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"phone_number {e}")
    return envelope(data=[_out(p) for p in crud.list_patients(db, last_name, date_of_birth, phone)])


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    p = crud.get_patient(db, patient_id)
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return envelope(data=_out(p))


@app.post("/patients", status_code=status.HTTP_201_CREATED)
def create_patient(payload: schemas.PatientCreate, db: Session = Depends(get_db)):
    existing = crud.get_patient_by_phone(db, payload.phone_number)
    if existing:
        raise HTTPException(status_code=409,
                            detail=f"A patient with this phone number already exists (patient_id={existing.patient_id})")
    try:
        p = crud.create_patient(db, payload)
    except crud.DuplicatePhoneError:
        raise HTTPException(status_code=409, detail="A patient with this phone number already exists")
    return envelope(data=_out(p))


@app.put("/patients/{patient_id}")
def update_patient(patient_id: str, payload: schemas.PatientUpdate, db: Session = Depends(get_db)):
    try:
        p = crud.update_patient(db, patient_id, payload)
    except crud.DuplicatePhoneError:
        raise HTTPException(status_code=409, detail="That phone number belongs to a different patient")
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return envelope(data=_out(p))


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    if not crud.soft_delete_patient(db, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    return envelope(data={"patient_id": patient_id, "deleted": True})


@app.get("/health")
def health():
    return {"status": "ok"}
