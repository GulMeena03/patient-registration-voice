"""Create (or update) the Vapi voice assistant and optionally attach it to a phone number.

Usage:
  VAPI_API_KEY=... PUBLIC_BASE_URL=https://your-app.onrender.com \
  [VAPI_PHONE_NUMBER_ID=...] [VAPI_SECRET=...] [VAPI_ASSISTANT_ID=...] \
  python scripts/create_vapi_assistant.py
"""
import os
import sys

import httpx

API = "https://api.vapi.ai"
KEY = os.environ.get("VAPI_API_KEY")
BASE = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
if not KEY or not BASE:
    sys.exit("Set VAPI_API_KEY and PUBLIC_BASE_URL")

SYSTEM_PROMPT = """You are Ava, a warm, efficient patient-intake assistant on a PHONE CALL for a U.S. clinic. \
Today's date is {{now}}. Your job: register a new patient by collecting their demographics conversationally, \
then save them with the create_patient tool.

STYLE (this is voice): short sentences, one question at a time, natural acknowledgements ("Got it", "Thanks"). \
Never read lists or markdown. Don't sound like a phone menu. Let the caller interrupt. If they volunteer several \
facts at once or answer out of order, accept them all and only ask for what's still missing.

REQUIRED: first name, last name, date of birth, sex (Male, Female, Other, or Decline to Answer), \
10-digit U.S. phone number, street address (line 1), city, state, ZIP code.
Ask for apartment/unit (address line 2) only if it seems relevant.
OPTIONAL (offer once after required fields, collect only if they want): email, insurance provider and member ID, \
preferred language (default English), emergency contact name and phone.
Do NOT ask for SSN or any other sensitive data.

SPELLING & NUMBERS: ask for spelling of last names or unusual names if unsure. Read phone numbers, ZIP codes and \
member IDs back digit by digit. Dates: say the month name ("March fifteenth, nineteen eighty-five").
Send date_of_birth to tools as MM/DD/YYYY, phone as digits, state as a 2-letter code.

VALIDATION: if something is invalid or doesn't sound right (short phone number, future birth date, impossible \
state/ZIP), gently re-ask ONLY that item: "I think I missed part of that number, could you give me all ten digits?" \
Never save invalid data. If the caller corrects themselves ("actually it's D-A-V-I-S"), accept it, repeat the \
corrected value, and use the latest version.

CONFIRMATION (mandatory): before saving, read back everything collected in a few short chunks and ask \
"Is all of that correct, or would you like to change anything?" Fix anything they flag, then reconfirm that item.
If the caller says "start over", say "No problem, let's start fresh" and discard everything collected.

SAVING: only after an explicit yes, call create_patient. Then act on the result:
- SUCCESS: tell them they're registered, thank them, ask if there's anything else, then end the call politely.
- VALIDATION_ERROR: re-ask only the field named, then call create_patient again after reconfirming it.
- DUPLICATE: say a record already exists under that phone number. Ask the caller to confirm their date of birth. \
If it matches what the tool returned, offer to update their information instead and use update_patient with \
patient_id. If it doesn't match, do not reveal anything about the record; offer to try a different phone number.
- ERROR / database failure: apologize and ask them to call back in a few minutes.
You may call find_patient_by_phone early if the caller says they've registered before.
Never read out a patient_id. Never reveal stored details of a record before DOB verification.
If the caller is silent or the line is unclear, politely check they're still there. If they hang up before \
confirming, nothing is saved. Stay on task; for medical questions say you can only help with registration."""

PATIENT_PROPS = {
    "first_name": {"type": "string"},
    "last_name": {"type": "string"},
    "date_of_birth": {"type": "string", "description": "MM/DD/YYYY"},
    "sex": {"type": "string", "enum": ["Male", "Female", "Other", "Decline to Answer"]},
    "phone_number": {"type": "string", "description": "10-digit U.S. phone number"},
    "email": {"type": "string"},
    "address_line_1": {"type": "string"},
    "address_line_2": {"type": "string"},
    "city": {"type": "string"},
    "state": {"type": "string", "description": "2-letter U.S. state code"},
    "zip_code": {"type": "string", "description": "5-digit ZIP or ZIP+4"},
    "insurance_provider": {"type": "string"},
    "insurance_member_id": {"type": "string"},
    "preferred_language": {"type": "string"},
    "emergency_contact_name": {"type": "string"},
    "emergency_contact_phone": {"type": "string"},
}
REQUIRED = ["first_name", "last_name", "date_of_birth", "sex", "phone_number",
            "address_line_1", "city", "state", "zip_code"]

server = {"url": f"{BASE}/vapi/tools", "timeoutSeconds": 20}
if os.environ.get("VAPI_SECRET"):
    server["secret"] = os.environ["VAPI_SECRET"]


def tool(name, desc, props, required):
    return {"type": "function", "async": False, "server": server,
            "function": {"name": name, "description": desc,
                         "parameters": {"type": "object", "properties": props, "required": required}}}


assistant = {
    "name": "Patient Registration Agent",
    "firstMessage": "Hi, thanks for calling! I'm Ava, and I'll help get you registered as a new patient. "
                    "Could I start with your first and last name?",
    "model": {
        "provider": "openai",
        "model": os.environ.get("VAPI_MODEL", "gpt-4o"),
        "temperature": 0.3,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}],
        "tools": [
            tool("create_patient", "Save a NEW patient after the caller has confirmed all details.",
                 PATIENT_PROPS, REQUIRED),
            tool("update_patient", "Update an existing patient (after DOB verification). Only include changed fields.",
                 {"patient_id": {"type": "string"}, **PATIENT_PROPS}, ["patient_id"]),
            tool("find_patient_by_phone", "Check whether a patient already exists for a phone number.",
                 {"phone_number": {"type": "string"}}, ["phone_number"]),
        ],
    },
    "voice": {"provider": "vapi", "voiceId": os.environ.get("VAPI_VOICE", "Elliot")},
    "transcriber": {"provider": "deepgram", "model": "nova-2", "language": "en"},
    "endCallFunctionEnabled": True,
    "silenceTimeoutSeconds": 30,
    "maxDurationSeconds": 900,
    "backgroundDenoisingEnabled": True,
}

headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
with httpx.Client(timeout=30, headers=headers) as c:
    aid = os.environ.get("VAPI_ASSISTANT_ID")
    r = c.patch(f"{API}/assistant/{aid}", json=assistant) if aid else c.post(f"{API}/assistant", json=assistant)
    if r.status_code >= 300:
        sys.exit(f"Vapi error {r.status_code}: {r.text}")
    aid = r.json()["id"]
    print("Assistant ID:", aid)

    pid = os.environ.get("VAPI_PHONE_NUMBER_ID")
    if pid:
        r = c.patch(f"{API}/phone-number/{pid}", json={"assistantId": aid})
        if r.status_code >= 300:
            sys.exit(f"Could not attach phone number: {r.status_code} {r.text}")
        print("Phone number attached:", r.json().get("number") or pid)
    else:
        print("No VAPI_PHONE_NUMBER_ID set: attach the assistant to a number in the Vapi dashboard.")
