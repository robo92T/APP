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

def test_home_office_auto_eight_hours_and_admin_enabled_field_gps(client,admin_headers,employee_session,monkeypatch):
    emp_id,employee_headers=employee_session
    class TestClock(datetime):
        current=datetime(2026,12,15,8,0,tzinfo=timezone.utc)
        @classmethod
        def now(cls,tz=None):
            return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)
    monkeypatch.setattr(remote_work,"datetime",TestClock)

    # Field GPS is disabled for every employee unless the administrator grants it.
    denied=client.post("/api/me/remote-punch",headers=employee_headers,json={
        "kind":"in","gps_lat":48.149,"gps_lon":17.103,
        "gps_accuracy_m":50,"gps_permission_confirmed":True})
    assert denied.status_code==403,denied.text
    initial=client.get("/api/me/remote-status",headers=employee_headers).json()
    assert initial["field_punch_enabled"] is False
    assert initial["remote_punch_enabled"] is False

    requested=client.post("/api/me/absences",headers=employee_headers,json={
        "kind":"home_office","start":"2026-12-15","end":"2026-12-15",
        "note":"Test práce z domu"})
    assert requested.status_code==201,requested.text
    assert requested.json()["status"]=="pending"
    approved=client.post(f"/api/absences/{requested.json()['id']}/approve",headers=admin_headers)
    assert approved.status_code==200,approved.text
    status=client.get("/api/me/remote-status",headers=employee_headers)
    assert status.status_code==200
    assert status.json()["approved_home_office"] is True
    assert status.json()["home_office_no_punch_required"] is True
    assert status.json()["remote_punch_enabled"] is False
    assert client.post("/api/me/remote-punch",headers=employee_headers,json={
        "kind":"in","gps_lat":48.149,"gps_lon":17.103,
        "gps_accuracy_m":50,"gps_permission_confirmed":True}).status_code==403

    attendance=client.get("/api/me/attendance?year=2026&month=12",headers=employee_headers)
    assert attendance.status_code==200,attendance.text
    home=next(r for r in attendance.json()["rows"] if r["day"]=="2026-12-15")
    assert home["worked_minutes"]==480
    assert home["home_office_auto_minutes"]==480
    assert home["in"] is None and home["out"] is None
    assert home["saldo_minutes"]==0  # 7.5h fund must not create fabricated overtime.
    admin_view=client.get(f"/api/admin/employee-calendar/{emp_id}?year=2026&month=12",headers=admin_headers)
    assert admin_view.status_code==200,admin_view.text
    assert next(r for r in admin_view.json()["rows"] if r["day"]=="2026-12-15")["home_office_auto_minutes"]==480

    # Only the administrator can explicitly grant the GPS button.
    assert client.get("/api/admin/field-punch-permissions",headers=employee_headers).status_code==403
    assert client.patch(f"/api/admin/field-punch-permissions/{emp_id}",
                        json={"enabled":True},headers=employee_headers).status_code==403
    granted=client.patch(f"/api/admin/field-punch-permissions/{emp_id}",
                         json={"enabled":True},headers=admin_headers)
    assert granted.status_code==200,granted.text
    assert granted.json()["enabled"] is True
    grants=client.get("/api/admin/field-punch-permissions",headers=admin_headers)
    assert grants.status_code==200
    assert next(p for p in grants.json() if p["employee_id"]==emp_id)["enabled"] is True

    # Even GPS-enabled employees never punch during an approved home-office day.
    still_blocked=client.post("/api/me/remote-punch",headers=employee_headers,json={
        "kind":"in","gps_lat":48.149,"gps_lon":17.103,
        "gps_accuracy_m":50,"gps_permission_confirmed":True})
    assert still_blocked.status_code==403

    # On a different field-work day, one-shot GPS is required; no tracking persists.
    TestClock.current=datetime(2026,12,16,8,0,tzinfo=timezone.utc)
    ready=client.get("/api/me/remote-status",headers=employee_headers)
    assert ready.status_code==200
    assert ready.json()["remote_punch_enabled"] is True
    assert ready.json()["field_punch_enabled"] is True
    assert ready.json()["approved_home_office"] is False
    assert client.post("/api/me/remote-punch",headers=employee_headers,json={"kind":"in"}).status_code==422
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
        assert e.origin=="field_gps"
        logs=session.scalars(select(Audit).where(Audit.action=="field_punch.record")).all()
        assert logs
        assert all("48.149" not in row.detail and "17.103" not in row.detail for row in logs)
    repeated=client.post("/api/me/remote-punch",headers=employee_headers,json={
        "kind":"in","gps_lat":48.149,"gps_lon":17.103,
        "gps_accuracy_m":50,"gps_permission_confirmed":True})
    assert repeated.status_code==429
    TestClock.current=datetime(2026,12,16,8,2,tzinfo=timezone.utc)
    left=client.post("/api/me/remote-punch",headers=employee_headers,json={
        "kind":"out","gps_lat":48.149,"gps_lon":17.103,
        "gps_accuracy_m":50,"gps_permission_confirmed":True})
    assert left.status_code==201,left.text
    assert left.json()["state"]=="off"
    revoked=client.patch(f"/api/admin/field-punch-permissions/{emp_id}",
                         json={"enabled":False},headers=admin_headers)
    assert revoked.status_code==200
    assert revoked.json()["enabled"] is False
    assert client.post("/api/me/remote-punch",headers=employee_headers,json={
        "kind":"in","gps_lat":48.149,"gps_lon":17.103,
        "gps_accuracy_m":50,"gps_permission_confirmed":True}).status_code==403

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
