# Voice AI Patient Registration

Call a real U.S. phone number, talk naturally, and get registered as a patient. The conversation is handled by
a [Vapi](https://vapi.ai) voice agent (STT + LLM + TTS + telephony); structured data is validated and stored by
a FastAPI backend and exposed through a REST API.

- **Phone number:** `<fill in after setup>`
- **API base URL:** `<fill in after deploy>` (interactive docs at `/docs`)

## Architecture

```
Caller ─ phone ─▶ Vapi (Deepgram STT → GPT-4o → TTS)
                      │  tool calls (create_patient / update_patient / find_patient_by_phone)
                      ▼
               FastAPI  /vapi/tools  ──▶  Pydantic validation ──▶ SQLite / Postgres
                      ▲
        REST /patients (list, get, create, update, soft-delete)
```

Design choices
- **Vapi** for the audio pipeline so effort goes into conversation quality and data integrity.
- **Two layers of validation:** the prompt makes the agent re-ask naturally; the server validates every tool call
  and returns `VALIDATION_ERROR: field: reason` so the LLM re-asks only that field. Nothing invalid is stored.
- **Normalization:** phones → `+1XXXXXXXXXX`, DOB accepts `MM/DD/YYYY` or ISO, state upper-cased, sex mapped to
  Male / Female / Other / Decline to Answer, email lower-cased.
- **Soft delete:** `deleted_at` timestamp; deleted patients vanish from all reads and free up their phone number
  (partial unique index on `phone_number WHERE deleted_at IS NULL`, works on SQLite and Postgres).
- **Duplicate detection (bonus):** same phone number → agent verifies DOB, then offers to update the existing record.
- **Responses** use `{"data": ..., "error": ...}` everywhere, including errors.
- Optional webhook auth via `VAPI_SECRET` (`X-Vapi-Secret` header).

## Run locally

```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m app.seed                                  # Jane Doe + Carlos Ramirez
uvicorn app.main:app --reload                       # http://localhost:8000/docs
pytest                                              # 14 tests
```

## Deploy (Render, free tier)

1. Push to GitHub → Render → **New → Blueprint** → select the repo (uses `render.yaml`: Docker web service + free Postgres).
2. Wait for deploy, then check `https://<your-app>.onrender.com/health`.
   (Free instances sleep when idle; hit `/health` a minute before demoing.)

Alternatives: Railway/Fly work with the included Dockerfile; set `DATABASE_URL` (Postgres) and `SEED_ON_START=true`.

## Create the voice agent

1. Create a Vapi account, copy your **private API key**, and get a phone number
   (Dashboard → Phone Numbers → free Vapi US number; copy its ID).
2. Run:
   ```bash
   export VAPI_API_KEY=... PUBLIC_BASE_URL=https://<your-app>.onrender.com
   export VAPI_PHONE_NUMBER_ID=...      # optional, attaches the assistant to the number
   export VAPI_SECRET=...               # optional, must match the VAPI_SECRET env var on the server
   python scripts/create_vapi_assistant.py
   ```
   Re-run with `VAPI_ASSISTANT_ID=<id>` to update the prompt/tools in place.
3. Call the number.

If a number can't be provisioned, use Vapi's in-dashboard **Talk to Assistant** / web call and document it
(the assessment allows a documented fallback).

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/patients` | filters: `last_name` (partial), `date_of_birth` (YYYY-MM-DD), `phone_number` |
| GET | `/patients/{id}` | 404 if missing/deleted |
| POST | `/patients` | 201; 409 if active phone already exists; 422 on validation |
| PUT | `/patients/{id}` | partial update |
| DELETE | `/patients/{id}` | soft delete |

```bash
curl "$API/patients?last_name=Doe"
curl -X POST "$API/patients" -H 'Content-Type: application/json' -d '{"first_name":"Ana","last_name":"Lopez","date_of_birth":"04/02/1992","sex":"Female","phone_number":"303-555-0142","address_line_1":"9 Pine Rd","city":"Denver","state":"CO","zip_code":"80202"}'
```

## Trade-offs & limitations

- Phone validation is NANP-format only (no carrier lookup); `555` test numbers are accepted on purpose.
- Duplicates are detected by phone only; name+DOB fuzzy matching would be better.
- Caller-ID isn't used to pre-fill the phone number (privacy / shared-line concerns).
- The REST API has no auth (webhook has optional shared secret); add OAuth/API keys before real use.
- Not HIPAA-compliant as built (no BAA'd vendors, encryption at rest, or audit log). Use fake data only.
- Free-tier hosting cold starts can delay the first tool call; warm it up before a demo.

## Next steps

Appointment scheduling after registration, Spanish-language mode, a small admin UI, audit log, rate limiting,
call transcripts/recordings linked to patient rows, and end-to-end tests with simulated callers.
