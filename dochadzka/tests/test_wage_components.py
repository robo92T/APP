"""Regression for wage time classifications in both consolidated report modes."""
import os
from fastapi.testclient import TestClient
import pytest

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

def test_daily_and_monthly_explicit_components(client,headers):
    people=client.get("/api/hr/employees",headers=headers).json()
    emp=people[0]
    day="2026-12-10"
    baseline=client.get("/api/group-report?mode=day&day="+day,headers=headers)
    assert baseline.status_code==200,baseline.text
    old=next(x for x in baseline.json()["rows"] if x["employee_id"]==emp["id"])
    payload={"employee_id":emp["id"],"day":day,"kind":"service_errand",
             "mode":"time_range","starts_at":"2026-12-10T09:00:00+01:00",
             "ends_at":"2026-12-10T11:30:00+01:00",
             "note":"Služobné rokovanie mimo pracoviska v meste"}
    created=client.post("/api/wage-components",headers=headers,json=payload)
    assert created.status_code==201,created.text
    cid=created.json()["id"]
    after=client.get("/api/group-report?mode=day&day="+day,headers=headers)
    assert after.status_code==200,after.text
    row=next(x for x in after.json()["rows"] if x["employee_id"]==emp["id"])
    assert row["service_errand_min"]==150
    assert row["saldo_min"]-old["saldo_min"]==min(150,max(0,old["planned_min"]-old["worked_min"]-old["credited_min"]))
    assert row["component"].startswith("Služobné dôvody")
    assert row["doctor_min"]>=0 and row["accompany_min"]>=0 and row["home_office_min"]>=0
    assert row["business_trip_min"]>=0 and row["travel_duration_min"]>=0
    same=client.post("/api/wage-components",headers=headers,json=payload)
    assert same.status_code==409
    month=client.get("/api/group-report?mode=month&year=2026&month=12",headers=headers)
    assert month.status_code==200,month.text
    row_month=next(x for x in month.json()["rows"] if x["employee_id"]==emp["id"])
    assert row_month["service_errand_min"]>=150
    assert "service_errand_min" in {x["key"] for x in month.json()["columns"]}
    export=client.get("/api/group-report/export?mode=day&day="+day+"&file_format=csv",headers=headers)
    assert export.status_code==200,export.text
    assert "Služobné dôvody" in export.content.decode("utf-8-sig")
    cancelled=client.post(f"/api/wage-components/{cid}/cancel",headers=headers,json={
        "reason":"Oprava testovacieho zapisu"})
    assert cancelled.status_code==200,cancelled.text
    restored=client.get("/api/group-report?mode=day&day="+day,headers=headers)
    assert restored.status_code==200
    assert next(x for x in restored.json()["rows"] if x["employee_id"]==emp["id"])["service_errand_min"]==0

def test_full_day_and_punched_classification(client,headers):
    employees=client.get("/api/hr/employees",headers=headers).json()
    emp=employees[1]
    full=client.post("/api/wage-components",headers=headers,json={
        "employee_id":emp["id"],"day":"2026-12-09",
        "kind":"business_trip","mode":"all_day",
        "note":"Celodenné pracovné rokovanie Bratislava"})
    assert full.status_code==201,full.text
    day=client.get("/api/group-report?mode=day&day=2026-12-09",headers=headers).json()
    line=next(x for x in day["rows"] if x["employee_id"]==emp["id"])
    assert line["business_trip_min"]==line["planned_min"]
    other=employees[2]
    punch=client.post("/api/wage-components",headers=headers,json={
        "employee_id":other["id"],"day":"2026-11-18",
        "kind":"home_office","mode":"punched",
        "note":"Remote work measured by actual completed punches"})
    assert punch.status_code==201,punch.text
    line=next(x for x in client.get("/api/group-report?mode=day&day=2026-11-18",headers=headers).json()["rows"]
        if x["employee_id"]==other["id"])
    assert line["home_office_min"]==line["worked_min"]

def test_two_nonoverlapping_payroll_reasons_same_day(client,headers):
    employees=client.get("/api/hr/employees",headers=headers).json()
    emp=employees[3]
    payload={"employee_id":emp["id"],"day":"2026-12-11","mode":"time_range",
      "kind":"doctor","starts_at":"2026-12-11T08:00:00+01:00",
      "ends_at":"2026-12-11T09:30:00+01:00","note":"Zdravotné vyšetrenie zamestnanca"}
    first=client.post("/api/wage-components",headers=headers,json=payload)
    assert first.status_code==201,first.text
    second=client.post("/api/wage-components",headers=headers,json={
      **payload,"kind":"service_errand",
      "starts_at":"2026-12-11T10:00:00+01:00",
      "ends_at":"2026-12-11T11:00:00+01:00",
      "note":"Služobné rokovanie mimo pracoviska"})
    assert second.status_code==201,second.text
    conflict=client.post("/api/wage-components",headers=headers,json={
      **payload,"kind":"accompany",
      "starts_at":"2026-12-11T09:00:00+01:00",
      "ends_at":"2026-12-11T11:30:00+01:00",
      "note":"Sprevádzanie rodinného príslušníka"})
    assert conflict.status_code==409,conflict.text
    report=client.get("/api/group-report?mode=day&day=2026-12-11",headers=headers)
    assert report.status_code==200,report.text
    row=next(x for x in report.json()["rows"] if x["employee_id"]==emp["id"])
    assert row["doctor_min"]==90
    assert row["service_errand_min"]==60
    assert row["credited_min"]<=row["planned_min"]

def test_medical_separate_column_and_access(client,headers):
    resp=client.get("/api/group-report?mode=day&day=2026-11-19",headers=headers)
    assert resp.status_code==200,resp.text
    assert {"doctor_min","accompany_min","home_office_min","service_errand_min","business_trip_min"}.issubset(
        {x["key"] for x in resp.json()["columns"]})
    assert client.get("/api/wage-components?year=2026&month=11").status_code==401
    assert client.post("/api/wage-components",json={}).status_code==401

def test_work_assignments_in_worked_not_paid_leave(client,headers):
    employees=client.get("/api/hr/employees",headers=headers).json()
    emp=employees[4]
    baseline=client.get("/api/group-report?mode=day&day=2026-12-16",headers=headers)
    assert baseline.status_code==200,baseline.text
    before=next(x for x in baseline.json()["rows"] if x["employee_id"]==emp["id"])
    manual=client.post("/api/wage-components",headers=headers,json={
        "employee_id":emp["id"],"day":"2026-12-16",
        "kind":"service_errand","mode":"time_range",
        "starts_at":"2026-12-16T08:30:00+01:00",
        "ends_at":"2026-12-16T11:30:00+01:00",
        "note":"Cesta na pracovné rokovanie mimo pracoviska"})
    assert manual.status_code==201,manual.text
    after=client.get("/api/group-report?mode=day&day=2026-12-16",headers=headers)
    assert after.status_code==200,after.text
    row=next(x for x in after.json()["rows"] if x["employee_id"]==emp["id"])
    expected=min(180,max(0,before["planned_min"]-before["worked_min"]-before["credited_min"]))
    assert row["worked_min"]==before["worked_min"]+expected
    assert row["credited_min"]==before["credited_min"]
    assert row["saldo_min"]-before["saldo_min"]==expected

def test_pn_and_ocr_as_separate_unworked_columns(client,headers):
    employees=client.get("/api/hr/employees",headers=headers).json()
    emp=employees[5]
    for date,kind,col in [("2026-12-21","sick","sick_min"),
                          ("2026-12-22","ocr","ocr_min")]:
        created=client.post("/api/absences",headers=headers,json={
            "employee_id":emp["id"],"kind":kind,
            "start":date,"end":date,"note":"Fiktívny test PN OČR"})
        assert created.status_code==200,created.text
        assert created.json()["status"]=="approved"
        report=client.get("/api/group-report?mode=day&day="+date,headers=headers)
        assert report.status_code==200,report.text
        row=next(x for x in report.json()["rows"] if x["employee_id"]==emp["id"])
        assert row[col]==row["planned_min"]
        assert row["credited_min"]==0
        assert row["worked_min"]==0
        assert col in {c["key"] for c in report.json()["columns"]}
    month=client.get("/api/group-report?mode=month&year=2026&month=12",headers=headers)
    assert month.status_code==200,month.text
    row=next(x for x in month.json()["rows"] if x["employee_id"]==emp["id"])
    assert row["sick_min"]>0 and row["ocr_min"]>0

def test_legacy_paid_medical_adds_credit_not_worked(client,headers):
    response=client.get("/api/group-report?mode=day&day=2026-11-19",headers=headers)
    assert response.status_code==200,response.text
    row=next(x for x in response.json()["rows"] if x["name"]=="Filip Ukážkový")
    assert row["doctor_min"]>=120
    assert row["credited_min"]>=120
    assert row["worked_min"]>=0
    assert row["saldo_min"]==row["worked_min"]+row["credited_min"]-row["planned_min"]

def test_no_stale_presence_on_next_day(client,headers):
    resp=client.get("/api/group-report?mode=day&day=2026-11-28",headers=headers)
    assert resp.status_code==200,resp.text
    for row in resp.json()["rows"]:
        assert not (row["status"]=="Na pracovisku*" and row["first_in"] is None)
