import os
os.environ["DATABASE_URL"] = "sqlite:///./test_patients.db"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app

client = TestClient(app)

VALID = {
    "first_name": "Test", "last_name": "User", "date_of_birth": "03/15/1990", "sex": "female",
    "phone_number": "(212) 555-0111", "address_line_1": "1 Test St", "city": "Testville",
    "state": "ca", "zip_code": "90210",
}


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def tool(name, args, call_id="c1"):
    body = {"message": {"type": "tool-calls", "toolCallList": [{"id": call_id, "name": name, "arguments": args}]}}
    return client.post("/vapi/tools", json=body).json()["results"][0]["result"]


def test_create_normalizes_and_gets():
    r = client.post("/patients", json=VALID)
    assert r.status_code == 201, r.text
    d = r.json()["data"]
    assert d["phone_number"] == "+12125550111" and d["state"] == "CA" and d["sex"] == "Female"
    assert d["date_of_birth"] == "1990-03-15"
    assert client.get(f"/patients/{d['patient_id']}").json()["data"]["first_name"] == "Test"


@pytest.mark.parametrize("field,value", [
    ("phone_number", "123"), ("date_of_birth", "01/01/2999"), ("state", "ZZ"),
    ("zip_code", "1234"), ("sex", "banana"), ("first_name", "R2D2"), ("email", "nope"),
])
def test_validation(field, value):
    r = client.post("/patients", json={**VALID, field: value})
    assert r.status_code == 422
    assert r.json()["data"] is None and r.json()["error"]


def test_duplicate_phone_409():
    client.post("/patients", json=VALID)
    assert client.post("/patients", json=VALID).status_code == 409


def test_soft_delete_and_reuse_phone():
    pid = client.post("/patients", json=VALID).json()["data"]["patient_id"]
    assert client.delete(f"/patients/{pid}").status_code == 200
    assert client.get(f"/patients/{pid}").status_code == 404
    assert client.get("/patients").json()["data"] == []
    assert client.post("/patients", json=VALID).status_code == 201  # phone free again


def test_update_and_filters():
    pid = client.post("/patients", json=VALID).json()["data"]["patient_id"]
    r = client.put(f"/patients/{pid}", json={"city": "Newtown", "email": "A@B.com"})
    assert r.json()["data"]["city"] == "Newtown" and r.json()["data"]["email"] == "a@b.com"
    assert len(client.get("/patients?last_name=use").json()["data"]) == 1
    assert len(client.get("/patients?date_of_birth=1990-03-15").json()["data"]) == 1
    assert len(client.get("/patients?phone_number=2125550111").json()["data"]) == 1
    assert client.get("/patients?last_name=zzz").json()["data"] == []
    assert client.put("/patients/nope", json={"city": "X"}).status_code == 404


def test_tool_create_duplicate_update_flow():
    assert tool("create_patient", VALID).startswith("SUCCESS")
    assert tool("create_patient", VALID).startswith("DUPLICATE")
    found = tool("find_patient_by_phone", {"phone_number": "212-555-0111"})
    assert found.startswith("FOUND") and "03/15/1990" in found
    pid = found.split("patient_id=")[1].split(",")[0]
    assert tool("update_patient", {"patient_id": pid, "city": "Elsewhere"}).startswith("SUCCESS")
    assert client.get(f"/patients/{pid}").json()["data"]["city"] == "Elsewhere"


def test_tool_validation_and_legacy_payload():
    assert tool("create_patient", {**VALID, "phone_number": "123"}).startswith("VALIDATION_ERROR")
    body = {"message": {"type": "tool-calls", "toolCalls": [
        {"id": "x", "function": {"name": "create_patient", "arguments": '{"first_name": "A"}'}}]}}
    res = client.post("/vapi/tools", json=body).json()["results"][0]
    assert res["toolCallId"] == "x" and res["result"].startswith("VALIDATION_ERROR")
    assert client.post("/vapi/tools", json={"message": {"type": "status-update"}}).json() == {}


def test_webhook_secret(monkeypatch):
    monkeypatch.setenv("VAPI_SECRET", "s3cret")
    body = {"message": {"type": "tool-calls", "toolCallList": []}}
    assert client.post("/vapi/tools", json=body).status_code == 401
    assert client.post("/vapi/tools", json=body, headers={"X-Vapi-Secret": "s3cret"}).status_code == 200
