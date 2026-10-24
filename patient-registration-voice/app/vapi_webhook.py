"""Vapi server-side tool webhook.

Vapi POSTs {"message": {"type": "tool-calls", "toolCallList": [...]}} (older payloads use
"toolCalls" with a nested "function"). We reply {"results": [{"toolCallId", "result"}]},
where `result` is a single-line string the LLM reads.
"""
import json
import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from . import crud, schemas
from .database import get_db

log = logging.getLogger("vapi")
router = APIRouter(prefix="/vapi", tags=["vapi"])


def _format_errors(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        field = ".".join(str(x) for x in err["loc"]) or "input"
        msg = err["msg"].replace("Value error, ", "")
        parts.append(f"{field}: {msg}")
    return "; ".join(parts)


def _extract_calls(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = message.get("toolCallList") or message.get("toolCalls") or []
    if not raw and message.get("toolWithToolCallList"):
        raw = [t.get("toolCall", {}) for t in message["toolWithToolCallList"]]
    calls = []
    for tc in raw:
        fn = tc.get("function") or tc
        args = fn.get("arguments") or fn.get("parameters") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                args = None
        calls.append({"id": tc.get("id", ""), "name": fn.get("name"), "args": args})
    return calls


def _create(args: dict, db: Session) -> str:
    try:
        data = schemas.PatientCreate(**args)
    except ValidationError as e:
        return f"VALIDATION_ERROR: {_format_errors(e)}. Ask the caller to restate only the invalid field(s)."
    existing = crud.get_patient_by_phone(db, data.phone_number)
    if existing:
        return (f"DUPLICATE: a record already exists for {existing.first_name} {existing.last_name} "
                f"with this phone number (patient_id={existing.patient_id}). Ask if they want to "
                f"update that record instead; verify date of birth first.")
    try:
        p = crud.create_patient(db, data)
    except crud.DuplicatePhoneError:
        return "DUPLICATE: this phone number is already registered."
    return f"SUCCESS: {p.first_name} {p.last_name} is registered (patient_id={p.patient_id})."


def _update(args: dict, db: Session) -> str:
    patient_id = args.pop("patient_id", None)
    if not patient_id:
        return "ERROR: patient_id is required. Call find_patient_by_phone first."
    clean = {k: v for k, v in args.items() if v not in (None, "")}
    if not clean:
        return "ERROR: no fields to update were provided."
    try:
        data = schemas.PatientUpdate(**clean)
    except ValidationError as e:
        return f"VALIDATION_ERROR: {_format_errors(e)}. Ask the caller to restate only the invalid field(s)."
    try:
        p = crud.update_patient(db, patient_id, data)
    except crud.DuplicatePhoneError:
        return "DUPLICATE: that phone number belongs to a different patient."
    if not p:
        return "ERROR: patient not found."
    return f"SUCCESS: record for {p.first_name} {p.last_name} updated."


def _find(args: dict, db: Session) -> str:
    try:
        phone = schemas.normalize_phone(args.get("phone_number", ""))
    except ValueError as e:
        return f"VALIDATION_ERROR: phone_number: {e}"
    p = crud.get_patient_by_phone(db, phone)
    if not p:
        return "NOT_FOUND: no existing patient with that phone number."
    return (f"FOUND: patient_id={p.patient_id}, first_name={p.first_name}, last_name={p.last_name}, "
            f"date_of_birth={p.date_of_birth.strftime('%m/%d/%Y')}. Verify the caller's date of birth "
            f"matches before updating; never read other record details aloud.")


TOOLS = {"create_patient": _create, "update_patient": _update, "find_patient_by_phone": _find}


@router.post("/tools")
async def handle_tool_calls(request: Request, db: Session = Depends(get_db),
                            x_vapi_secret: str = Header(default="")):
    secret = os.getenv("VAPI_SECRET", "")
    if secret and x_vapi_secret != secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    payload = await request.json()
    message = payload.get("message", {})
    if message.get("type") not in (None, "tool-calls"):
        return {}  # ignore other Vapi server messages

    results = []
    for call in _extract_calls(message):
        fn = TOOLS.get(call["name"])
        if fn is None:
            result = f"ERROR: unknown tool {call['name']}"
        elif not isinstance(call["args"], dict):
            result = "ERROR: arguments were not valid JSON."
        else:
            try:
                result = fn(dict(call["args"]), db)
            except Exception:  # never let the call crash mid-conversation
                log.exception("tool %s failed", call["name"])
                db.rollback()
                result = "ERROR: database failure. Apologize and ask the caller to try again shortly."
        log.info("tool=%s -> %s", call["name"], result[:120])
        results.append({"toolCallId": call["id"], "result": result})
    return {"results": results}
