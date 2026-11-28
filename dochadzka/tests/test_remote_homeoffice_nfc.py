"""Self-service HO authorization, explicit location minimization and NFC assignment."""
import os
from datetime import datetime, timezone
from fastapi.testclient import TestClient
import pytest
import remote_work

@pytest.fixture(scope="module")
def client():
    from main import app
    return TestClient(app)

@pytest.fixture(scope="module")
def admin_headers(client):
    response=client.post("/api/auth/login",json={
        "username":os.environ["BOOTSTRAP_ADMIN_USERNAME"],
        "password":os.environ["BOOTSTRAP_ADMIN_PASSWORD"]})
    assert response.status_code==200,response.text
    return {"Authorization":"Bearer "+response.json()["access_token"]}

@pytest.fixture(scope="module")
def employee_session(client,admin_headers):
    people=client.get("/api/hr/employees",headers=admin_headers).json()
    employee_id=people[0]["id"]
    credentials={"username":"test-homeoffice-employee","password":"TestOnlyHomeOfficePass2026!"}
    created=client.post(f"/api/auth/accounts?role=employee&employee_id={employee_id}",
        headers=admin_headers,json=credentials)
    assert created.status_code==200,created.text
    logged=client.post("/api/auth/login",json=credentials)
    assert logged.status_code==200,logged.text
    employee_headers={"Authorization":"Bearer "+logged.json()["access_token"]}
    changed=client.post("/api/auth/password",headers=employee_headers,json={
        "old_password":credentials["password"],"new_password":"ChangedOnlyForHomeOfficeTest2026!"})
    assert changed.status_code==200,changed.text
    return employee_id,employee_headers

def test_home_office_approved_day_required_and_server_clock(client,admin_headers,employee_session,monkeypatch):
    emp_id,employee_headers=employee_session
    class TestClock(datetime):
        current=datetime(2026,12,15,8,0,tzinfo=timezone.utc)
        @classmethod
        def now(cls,tz=None):
            return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)
    monkeypatch.setattr(remote_work,"datetime",TestClock)
    denied=client.post("/api/me/remote-punch",headers=employee_headers,json={"kind":"in"})
    assert denied.status_code==403,denied.text
    requested=client.post("/api/me/absences",headers=employee_headers,json={
        "kind":"home_office","start":"2026-12-15","end":"2026-12-15",
        "note":"Test prace z domu"})
    assert requested.status_code==201,requested.text
    assert requested.json()["status"]=="pending"
    still=client.post("/api/me/remote-punch",headers=employee_headers,json={"kind":"in"})
    assert still.status_code==403
    approved=client.post(f"/api/absences/{requested.json()['id']}/approve",headers=admin_headers)
    assert approved.status_code==200,approved.text
    ready=client.get("/api/me/remote-status",headers=employee_headers)
    assert ready.status_code==200
    assert ready.json()["remote_punch_enabled"] is True
    entered=client.post("/api/me/remote-punch",headers=employee_headers,json={
        "kind":"in","gps_lat":48.149,"gps_lon":17.103,
        "gps_accuracy_m":50,"gps_permission_confirmed":True})
    assert entered.status_code==201,entered.text
    assert entered.json()["gps_saved"] is False
    assert entered.json()["state"]=="working"
    from main import SessionLocal,Audit,Event
    from sqlalchemy import select
    with SessionLocal() as session:
        e=session.get(Event,entered.json()["id"])
        assert e.origin=="home_office_web"
        logs=session.scalars(select(Audit).where(Audit.action=="home_office.punch")).all()
        assert logs
        assert all("48.149" not in row.detail and "17.103" not in row.detail for row in logs)
    repeated=client.post("/api/me/remote-punch",headers=employee_headers,json={"kind":"in"})
    assert repeated.status_code==429
    TestClock.current=datetime(2026,12,15,8,2,tzinfo=timezone.utc)
    left=client.post("/api/me/remote-punch",headers=employee_headers,json={"kind":"out"})
    assert left.status_code==201,left.text
    assert left.json()["state"]=="off"

def test_employee_nfc_assignment_requires_hr(client,admin_headers,employee_session):
    emp_id,employee_headers=employee_session
    uid="04:A1:B2:C3:D4"
    assert client.post("/api/hr/nfc/assign",headers=employee_headers,json={
        "employee_id":emp_id,"tag_uid":uid}).status_code==403
    result=client.post("/api/hr/nfc/assign",headers=admin_headers,json={
        "employee_id":emp_id,"tag_uid":uid})
    assert result.status_code==200,result.text
    assert result.json()["assigned"]
    duplicate=client.post("/api/hr/nfc/assign",headers=admin_headers,json={
        "employee_id":emp_id+1,"tag_uid":uid})
    assert duplicate.status_code==409,duplicate.text

def test_user_cannot_choose_arbitrary_employee_id(client,employee_session):
    _,headers=employee_session
    status=client.get("/api/me/remote-status",headers=headers)
    assert status.status_code==200
    assert "employee_id" not in status.json()
    assert client.post("/api/me/remote-punch",json={"kind":"in"}).status_code==401
