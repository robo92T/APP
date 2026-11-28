"""BID shift profiles: 8+0.5h TPP, dispatcher 11+1h, role separation, statutory premium calculator."""
import os
from datetime import datetime,date,timezone
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from pdf_reports import build_rows
from work_rules import SHIFT_PRESETS,expected_break,classify_agreement
from premiums import summary

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

def event(kind,iso,id):
    return SimpleNamespace(kind=kind,at=datetime.fromisoformat(iso),id=id)

def employee(regime="fixed"):
    return SimpleNamespace(id=1,name="Ukážka",weekly_minutes=2400,
        work_days=5,start_date=date(2026,1,1),end_date=None,work_regime=regime)

def test_tpp_auto_lunch_without_break_punch():
    e=employee()
    events=[event("in","2026-11-25T08:00:00+01:00",1),
            event("out","2026-11-25T16:30:00+01:00",2)]
    rows=build_rows(e,events,{},[],2026,11)
    r=next(x for x in rows if x["day"]==date(2026,11,25))
    assert r["worked"]==480
    assert r["breaks"]==30
    assert r["plan"]==480
    assert r["saldo"]==0

def test_explicit_lunch_not_deducted_twice():
    events=[event("in","2026-11-25T08:00:00+01:00",1),
      event("break_start","2026-11-25T12:00:00+01:00",2),
      event("break_end","2026-11-25T12:30:00+01:00",3),
      event("out","2026-11-25T16:30:00+01:00",4)]
    r=next(x for x in build_rows(employee(),events,{},[],2026,11)
            if x["day"]==date(2026,11,25))
    assert r["worked"]==480
    assert r["breaks"]==30

def test_dispatcher_one_hour_auto_break_and_night_premium():
    e=employee("dispatcher")
    sh=SimpleNamespace(start_time="18:00",end_time="06:00",planned_minutes=660)
    ev=[event("in","2026-11-25T18:00:00+01:00",1),
        event("out","2026-11-26T06:00:00+01:00",2)]
    r=build_rows(e,ev,{date(2026,11,25):sh},[],2026,11)
    assert sum(x["worked"] for x in r)==660
    assert sum(x["breaks"] for x in r)==60
    assert sum(x["plan"] for x in r)==660
    d=summary(ev,e,{date(2026,11,25):sh},2026,11,average_hourly=12)
    assert d["worked_min"]==660
    assert d["night_min"]>0
    assert d["amounts"]["night_eur"]>0

def test_half_shift_has_no_lunch_break():
    e=employee("dispatcher")
    ev=[event("in","2026-11-25T06:00:00+01:00",1),
        event("out","2026-11-25T12:00:00+01:00",2)]
    r=next(x for x in build_rows(e,ev,{},[],2026,11) if x["day"]==date(2026,11,25))
    assert r["worked"]==360 and r["breaks"]==0

def test_dispatcher_presets_and_dohoda_limits():
    assert SHIFT_PRESETS["dispatch_day"]["planned_minutes"]==660
    assert SHIFT_PRESETS["dispatch_day"]["break_minutes"]==60
    assert SHIFT_PRESETS["tpp"]["planned_minutes"]==480
    assert classify_agreement("agreement_activity",2400)
    assert classify_agreement("agreement_seasonal",2400) is None
    assert classify_agreement("agreement_task",2400)

def test_scheduler_role_scope_and_shift_save(client,headers):
    employees=client.get("/api/hr/employees",headers=headers).json()
    e=employees[0]
    cred={"username":"test-shift-planner","password":"SchedulerPassOnly2026!"}
    created=client.post("/api/auth/accounts?role=scheduler",headers=headers,json=cred)
    assert created.status_code==200,created.text
    login=client.post("/api/auth/login",json=cred)
    assert login.status_code==200,login.text
    auth={"Authorization":"Bearer "+login.json()["access_token"]}
    changed=client.post("/api/auth/password",headers=auth,json={
        "old_password":cred["password"],"new_password":"SchedulerChangedPassOnly2026!"})
    assert changed.status_code==200,changed.text
    assert client.get("/api/scheduler/employees",headers=auth).status_code==200
    assert client.get("/api/shift-presets",headers=auth).status_code==200
    assert client.get("/api/hr/employees",headers=auth).status_code==403
    assert client.get("/api/payroll/months",headers=auth).status_code==403
    result=client.post("/api/shifts",headers=auth,json={"employee_id":e["id"],"day":"2027-03-03",
        "planned_minutes":660,"start_time":"06:00","end_time":"18:00","preset":"dispatch_day"})
    assert result.status_code==200,result.text
    invalid=client.post("/api/shifts",headers=auth,json={"employee_id":e["id"],"day":"2027-03-04",
        "planned_minutes":720,"start_time":"06:00","end_time":"18:00"})
    assert invalid.status_code==422
    scope=client.get("/api/shifts?start=2027-03-01&end=2027-03-31",headers=auth)
    assert scope.status_code==200
    assert any(x["planned_minutes"]==660 for x in scope.json())

def test_legal_premiums_authorized_only(client,headers):
    employees=client.get("/api/hr/employees",headers=headers).json()
    e=employees[0]["id"]
    r=client.get(f"/api/premiums/{e}?year=2026&month=11&average_hourly=10",headers=headers)
    assert r.status_code==200,r.text
    assert set(r.json()["amounts"])=={"night_eur","saturday_eur","sunday_eur","holiday_eur"}
    assert client.get(f"/api/premiums/{e}?year=2026&month=11").status_code==401
    assert client.get(f"/api/premiums/{e}?year=2027&month=1",headers=headers).status_code==422
