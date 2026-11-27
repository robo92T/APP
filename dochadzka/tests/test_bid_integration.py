"""Integration smoke tests use isolated SQLite test data only (CI demo mode)."""
import os
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    from main import app
    return TestClient(app)

@pytest.fixture(scope="module")
def admin_headers(client):
    response=client.post("/api/auth/login",json={
        "username":os.environ.get("BOOTSTRAP_ADMIN_USERNAME","ci-admin"),
        "password":os.environ.get("BOOTSTRAP_ADMIN_PASSWORD","TestOnlyPassword2026!")
    })
    assert response.status_code==200,response.text
    token=response.json()["access_token"]
    return {"Authorization":"Bearer "+token}

def test_public_health(client):
    response=client.get("/health")
    assert response.status_code==200
    assert response.json()["status"]=="ok"

def test_ten_fictional_employees(client,admin_headers):
    response=client.get("/api/hr/employees",headers=admin_headers)
    assert response.status_code==200,response.text
    people=response.json()
    assert len(people)==10
    assert all(str(p["personal_number"]).startswith("D") for p in people)
    assert all(p["email"].endswith("@example.invalid") for p in people)

def test_organization_demo(client,admin_headers):
    response=client.get("/api/org/units",headers=admin_headers)
    assert response.status_code==200,response.text
    assert len(response.json())>=6

def test_payroll_export_profiles(client,admin_headers):
    profiles=client.get("/api/exports/profiles",headers=admin_headers)
    assert profiles.status_code==200,profiles.text
    records=profiles.json()
    assert {p["format"] for p in records}=={"csv","xlsx","json","xml"}
    p=next(x for x in records if x["format"]=="csv")
    response=client.get(f"/api/exports/download/{p['id']}?year=2026&month=11",headers=admin_headers)
    assert response.status_code==200,response.text
    assert b"D1001" in response.content
    assert response.headers["cache-control"]=="no-store"

def test_legal_calendar_2026(client,admin_headers):
    response=client.get("/api/legal/calendar/2026",headers=admin_headers)
    assert response.status_code==200,response.text
    dates={x["date"]:x for x in response.json()["holidays"]}
    assert dates["2026-05-08"]["is_day_off"] is False
    assert dates["2026-05-08"]["premium_reference"] is True
    assert dates["2026-09-15"]["is_day_off"] is False

def test_quality_checks(client,admin_headers):
    response=client.get("/api/quality/monthly?year=2026&month=11",headers=admin_headers)
    assert response.status_code==200,response.text
    assert isinstance(response.json()["findings"],list)

def test_employee_data_denied_without_token(client):
    for endpoint in ("/api/hr/employees","/api/org/units","/api/exports/profiles",
                     "/api/quality/monthly?year=2026&month=11"):
        response=client.get(endpoint)
        assert response.status_code==401,(endpoint,response.text)
