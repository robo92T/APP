"""Group overview integration: row-by-employee, daily status, department, monthly totals and file exports."""
import os
from datetime import date
from fastapi.testclient import TestClient
import pytest

@pytest.fixture(scope="module")
def client():
    from main import app
    return TestClient(app)

@pytest.fixture(scope="module")
def headers(client):
    resp=client.post("/api/auth/login",json={
        "username":os.environ.get("BOOTSTRAP_ADMIN_USERNAME","ci-admin"),
        "password":os.environ.get("BOOTSTRAP_ADMIN_PASSWORD","TestOnlyPassword2026!")
    })
    assert resp.status_code==200,resp.text
    return {"Authorization":"Bearer "+resp.json()["access_token"]}

def test_daily_all_employee_rows_and_absence_component(client,headers):
    response=client.get("/api/group-report?mode=day&day=2026-11-12",headers=headers)
    assert response.status_code==200,response.text
    body=response.json()
    assert body["mode"]=="day"
    assert body["counts"]["total"]==len(body["rows"])==10
    assert len({r["employee_id"] for r in body["rows"]})==10
    assert {"name","department","first_in","last_out","worked_min","planned_min","break_min","component","status","status_key"}.issubset(body["rows"][0])
    leave=[r for r in body["rows"] if r["personal_number"]=="D1001"][0]
    assert leave["status_key"]=="absent"
    assert leave["component"]=="Dovolenka"
    assert leave["credited_min"]>0
    assert leave["department"]=="Personalistika a mzdy"

def test_monthly_all_employee_rows_and_components(client,headers):
    response=client.get("/api/group-report?mode=month&year=2026&month=11",headers=headers)
    assert response.status_code==200,response.text
    body=response.json()
    assert body["mode"]=="month"
    assert len(body["rows"])==10
    assert body["totals"]["worked_min"]>0
    assert body["totals"]["planned_min"]>0
    keys={c["key"] for c in body["columns"]}
    assert {"worked_min","night_min","saturday_min","vacation_min","doctor_min","credited_min","saldo_min"}.issubset(keys)

@pytest.mark.parametrize("file_format,magic",[
    ("csv",b"\xef\xbb\xbf"),
    ("xlsx",b"PK"),
])
def test_export(client,headers,file_format,magic):
    r=client.get("/api/group-report/export?mode=day&day=2026-11-12&file_format="+file_format,headers=headers)
    assert r.status_code==200,r.text
    assert r.content.startswith(magic)
    assert r.headers["cache-control"]=="no-store"

def test_other_roles_cannot_list_staff(client):
    assert client.get("/api/group-report?mode=day&day=2026-11-12").status_code==401
    assert client.get("/api/group-report/export?mode=day&day=2026-11-12").status_code==401
