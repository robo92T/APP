"""Aktion-style audit workflow and safe bulk planning on fictional isolated demo data."""
import os
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    from main import app
    return TestClient(app)

@pytest.fixture(scope="module")
def headers(client):
    response=client.post("/api/auth/login",json={
        "username":os.environ["BOOTSTRAP_ADMIN_USERNAME"],
        "password":os.environ["BOOTSTRAP_ADMIN_PASSWORD"]})
    assert response.status_code==200,response.text
    return {"Authorization":"Bearer "+response.json()["access_token"]}

def test_reviewer_confirm_before_month_close(client,headers):
    period=client.get("/api/workflow/month/2026/11",headers=headers)
    assert period.status_code==200,period.text
    assert len(period.json()["rows"])==10
    identity=period.json()["rows"][0]["employee_id"]
    initial=client.post("/api/workflow/confirm",headers=headers,json={
        "employee_id":identity,"year":2026,"month":11,"note":"HR"})
    assert initial.status_code==409
    reviewed=client.post("/api/workflow/review",headers=headers,json={
        "employee_id":identity,"year":2026,"month":11,"note":"Kontrola výkazu test"})
    assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()["status"]=="reviewed"
    confirmed=client.post("/api/workflow/confirm",headers=headers,json={
        "employee_id":identity,"year":2026,"month":11,"note":"Kontrola manažérom"})
    assert confirmed.status_code==200,confirmed.text
    assert confirmed.json()["status"]=="confirmed"
    status=client.get("/api/workflow/close-precheck/2026/11",headers=headers)
    assert status.status_code==200
    assert not status.json()["ready"]
    unlocked=client.post("/api/workflow/unconfirm",headers=headers,json={
        "employee_id":identity,"year":2026,"month":11,"note":"Opravný testovací postup"})
    assert unlocked.status_code==200,unlocked.text
    assert unlocked.json()["status"]=="pending"

def test_bulk_absence_preview_and_atomic_write(client,headers):
    people=client.get("/api/hr/employees",headers=headers).json()
    ids=[p["id"] for p in people[:2]]
    # Outside fictional seeded November; safe two-person December simulation.
    payload={"employee_ids":ids,"kind":"training","start":"2026-12-17",
       "end":"2026-12-17","reason":"Fiktívne školenie tímu", "dry_run":True}
    check=client.post("/api/bulk-absence",headers=headers,json=payload)
    assert check.status_code==200,check.text
    assert check.json()["count"]==2
    save=client.post("/api/bulk-absence",headers=headers,json={**payload,"dry_run":False})
    assert save.status_code==200,save.text
    duplicate=client.post("/api/bulk-absence",headers=headers,json={**payload,"dry_run":False})
    assert duplicate.status_code==409,duplicate.text

def test_bulk_absence_rejects_duplicate_employee_ids(client,headers):
    people=client.get("/api/hr/employees",headers=headers).json()
    employee_id=people[0]["id"]
    result=client.post("/api/bulk-absence",headers=headers,json={
        "employee_ids":[employee_id,employee_id],"kind":"training",
        "start":"2026-12-20","end":"2026-12-20",
        "reason":"Fiktívny test duplicity","dry_run":True})
    assert result.status_code==422

def test_security_without_token(client):
    assert client.get("/api/workflow/month/2026/11").status_code==401
    assert client.post("/api/bulk-absence",json={}).status_code==401
