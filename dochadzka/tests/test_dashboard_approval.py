"""Admin quick approval/rejection: backend authorization and state workflow."""
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

def test_approve_then_reject_pending_requests_from_dashboard(client,headers):
    employees=client.get("/api/hr/employees",headers=headers).json()
    employee_id=employees[1]["id"]
    payload={"employee_id":employee_id,"kind":"vacation",
             "start":"2027-02-16","end":"2027-02-16",
             "note":"Test schvaľovania z prehľadu"}
    created=client.post("/api/absences",headers=headers,json=payload)
    assert created.status_code==200,created.text
    item=created.json()
    assert item["status"]=="pending"
    approved=client.post(f"/api/absences/{item['id']}/approve",headers=headers)
    assert approved.status_code==200,approved.text
    assert approved.json()["status"]=="approved"
    again=client.post(f"/api/absences/{item['id']}/approve",headers=headers)
    assert again.status_code==409
    other=client.post("/api/absences",headers=headers,json={
        **payload,"start":"2027-02-17","end":"2027-02-17"})
    assert other.status_code==200,other.text
    rejected=client.post(f"/api/absences/{other.json()['id']}/reject",headers=headers)
    assert rejected.status_code==200,rejected.text
    assert rejected.json()["status"]=="rejected"
    all_items=client.get("/api/absences",headers=headers)
    assert all_items.status_code==200,all_items.text
    by_id={x["id"]:x for x in all_items.json()}
    assert by_id[item["id"]]["status"]=="approved"
    assert by_id[other.json()["id"]]["status"]=="rejected"
    from main import SessionLocal,Audit
    from sqlalchemy import select
    with SessionLocal() as db:
        events=db.scalars(select(Audit).where(Audit.action.in_(
            ["absence.approve","absence.reject"]))).all()
        assert any(str(item["id"]) in x.detail for x in events)
        assert any(x.actor==os.environ["BOOTSTRAP_ADMIN_USERNAME"] for x in events)

def test_approval_restricted_without_authentication(client):
    assert client.post("/api/absences/1/approve").status_code==401
    assert client.post("/api/absences/1/reject").status_code==401
