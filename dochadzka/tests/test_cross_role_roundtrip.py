"""Isolated round-trip between fictitious employee and administrator."""
import os
from fastapi.testclient import TestClient
from main import app

def login(c,user,password):
    r=c.post("/api/auth/login",json={"username":user,"password":password})
    assert r.status_code==200,r.text
    return r.json(),{"Authorization":"Bearer "+r.json()["access_token"]}

def own_request(c,h,ident):
    r=c.get("/api/me/calendar?year=2027&month=6",headers=h)
    assert r.status_code==200,r.text
    return next(x for x in r.json()["absences"] if x["id"]==ident)

def admin_request(c,h,ident):
    r=c.get("/api/absences",headers=h)
    assert r.status_code==200,r.text
    return next(x for x in r.json() if x["id"]==ident)

def send(c,h,kind,date,minutes=None):
    r=c.post("/api/me/absences",headers=h,json={
        "kind":kind,"start":date,"end":date,"minutes":minutes,"note":"CI role synchronization test"})
    assert r.status_code==201,r.text
    assert r.json()["status"]=="pending"
    return r.json()["id"]

def test_employee_admin_employee_approval_and_rejection():
    with TestClient(app) as c:
        adm,ah=login(c,os.environ["BOOTSTRAP_ADMIN_USERNAME"],os.environ["BOOTSTRAP_ADMIN_PASSWORD"])
        emp,eh=login(c,"demo.zamestnanec",os.environ["DEMO_EMPLOYEE_PASSWORD"])
        eid=emp["employee_id"]
        assert adm["role"]=="admin" and emp["role"]=="employee"
        assert isinstance(eid,int) and eid>0
        assert c.get("/health").status_code==200
        assert c.get("/api/employees",headers=ah).status_code==200
        assert c.get("/api/employees",headers=eh).status_code==403
        assert c.get("/api/me/summary",headers=eh).status_code==200
        assert c.get(f"/api/admin/employee-calendar/{eid}?year=2027&month=6",headers=eh).status_code==403

        # Employee sends -> admin sees pending -> admin approves -> employee sees approved.
        vac=send(c,eh,"vacation","2027-06-08")
        assert own_request(c,eh,vac)["status"]=="pending"
        assert admin_request(c,ah,vac)["status"]=="pending"
        assert admin_request(c,ah,vac)["employee_id"]==eid
        result=c.post(f"/api/absences/{vac}/approve",headers=ah)
        assert result.status_code==200,result.text
        assert result.json()["status"]=="approved"
        assert own_request(c,eh,vac)["status"]=="approved"
        assert admin_request(c,ah,vac)["status"]=="approved"
        admincal=c.get(f"/api/admin/employee-calendar/{eid}?year=2027&month=6",headers=ah)
        assert admincal.status_code==200,admincal.text
        assert any(x["id"]==vac and x["status"]=="approved" for x in admincal.json()["absences"])
        assert c.post(f"/api/absences/{vac}/approve",headers=eh).status_code==403
        assert c.post(f"/api/absences/{vac}/approve",headers=ah).status_code==409

        # Admin rejects another employee-submitted request -> employee sees rejection.
        doctor=send(c,eh,"doctor","2027-06-09",minutes=120)
        assert admin_request(c,ah,doctor)["status"]=="pending"
        rejected=c.post(f"/api/absences/{doctor}/reject",headers=ah)
        assert rejected.status_code==200,rejected.text
        assert own_request(c,eh,doctor)["status"]=="rejected"
        assert admin_request(c,ah,doctor)["status"]=="rejected"

        # Approved home office changes both monthly views to 8 hours, without GPS.
        home=send(c,eh,"home_office","2027-06-10")
        before=c.get("/api/me/attendance?year=2027&month=6",headers=eh)
        assert before.status_code==200
        assert next(x for x in before.json()["rows"] if x["day"]=="2027-06-10")["worked_minutes"]==0
        accepted=c.post(f"/api/absences/{home}/approve",headers=ah)
        assert accepted.status_code==200,accepted.text
        employee_day=next(x for x in c.get("/api/me/attendance?year=2027&month=6",headers=eh).json()["rows"] if x["day"]=="2027-06-10")
        admin_day=next(x for x in c.get(f"/api/admin/employee-calendar/{eid}?year=2027&month=6",headers=ah).json()["rows"] if x["day"]=="2027-06-10")
        for day in (employee_day,admin_day):
            assert day["home_office_auto_minutes"]==480
            assert day["worked_minutes"]==480
            assert day["in"] is None and day["out"] is None
        assert own_request(c,eh,home)["status"]=="approved"

        # Unauthorized employee cannot manage the GPS privilege or inspect admin data.
        assert c.get("/api/admin/field-punch-permissions",headers=eh).status_code==403
        assert c.get("/api/absences",headers=eh).status_code==403
        assert c.get("/api/admin/field-punch-permissions",headers=ah).status_code==200
        assert c.get(f"/api/balances/{eid}/2027",headers=ah).status_code==200
        assert c.get("/api/calendar/2027",headers=ah).status_code==200
