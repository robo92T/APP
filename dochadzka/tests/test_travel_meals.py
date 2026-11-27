"""Legally bounded domestic allowances; test DB is isolated by tests/conftest.py."""
from datetime import date
import os
import pytest
from fastapi.testclient import TestClient
from travel import compute_domestic_day,daily_intervals,applicable_rates
from decimal import Decimal

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

def test_new_allowance_on_december_first():
    assert applicable_rates(date(2026,11,30))[1:4]==(
        Decimal("9.30"),Decimal("13.80"),Decimal("20.60"))
    assert applicable_rates(date(2026,12,1))[1:4]==(
        Decimal("9.80"),Decimal("14.60"),Decimal("21.70"))

def test_domestic_bands_and_meal_deductions():
    d=date(2026,12,4)
    assert compute_domestic_day(d,299)["meal_allowance_eur"]==0
    assert compute_domestic_day(d,300)["meal_allowance_eur"]==9.80
    assert compute_domestic_day(d,720)["meal_allowance_eur"]==9.80
    assert compute_domestic_day(d,721)["meal_allowance_eur"]==14.60
    assert compute_domestic_day(d,1081)["meal_allowance_eur"]==21.70
    # Lunch is deducted from the HIGHEST bracket, not from 5-12h.
    assert compute_domestic_day(d,400,lunch=True)["meal_allowance_eur"]==1.12
    assert compute_domestic_day(d,400,breakfast=True,lunch=True,dinner=True)["meal_allowance_eur"]==0

def test_trip_spanning_midnight_has_two_day_allowances():
    from datetime import datetime
    start=datetime.fromisoformat("2026-11-30T16:00:00+01:00")
    end=datetime.fromisoformat("2026-12-01T10:00:00+01:00")
    lines=list(daily_intervals(start,end))
    assert [(str(d),minutes) for d,minutes in lines]==[
        ("2026-11-30",480),("2026-12-01",600)]
    assert sum(compute_domestic_day(d,m)["meal_allowance_eur"] for d,m in lines)==19.1

def test_admin_trip_approval_and_meal_ledger(client,headers):
    employees=client.get("/api/hr/employees",headers=headers).json()
    eid=employees[0]["id"]
    trip=client.post("/api/travel",headers=headers,json={
        "employee_id":eid,"purpose":"Fiktívna testovacia pracovná cesta",
        "destination":"Trnava","starts_at":"2026-12-08T08:00:00+01:00",
        "ends_at":"2026-12-08T17:00:00+01:00",
        "transport":"private_car","private_car_km":"100",
        "fuel_l_per_100km":"6","fuel_price_eur_l":"1.60",
        "public_transport_eur":"0","lodging_eur":"0","other_expenses_eur":"2.50","advance_eur":"0"})
    assert trip.status_code==200,trip.text
    t=trip.json()
    assert t["meal_allowance_eur"]==9.8
    assert t["mileage_eur"]==31.3
    assert t["fuel_eur"]==9.6
    assert t["expenses_eur"]==2.5
    assert t["travel_total_eur"]==53.2
    id=t["id"]
    meal=client.put(f"/api/travel/{id}/meal",headers=headers,json={
        "day":"2026-12-08","breakfast":False,"lunch":True,"dinner":False})
    assert meal.status_code==200,meal.text
    assert meal.json()["meal_allowance_eur"]==1.12
    approved=client.post(f"/api/travel/{id}/approve",headers=headers,
        json={"reason":"HR overilo všetky fiktívne cestovné doklady"})
    assert approved.status_code==200,approved.text
    summary=client.get("/api/meals/month?year=2026&month=12",headers=headers)
    assert summary.status_code==200,summary.text
    person=next(x for x in summary.json()["employees"] if x["employee_id"]==eid)
    day=next(x for x in person["days"] if x["day"]=="2026-12-08")
    assert day["meal_ticket_eligible"] is False
    assert day["trip_meal_eur"]==1.12

def test_meal_ticket_more_than_four_hours_and_no_duplicate_on_travel(client,headers):
    r=client.get("/api/meals/month?year=2026&month=11",headers=headers)
    assert r.status_code==200,r.text
    data=r.json()
    assert len(data["employees"])==10
    assert data["total_tickets"]>0
    emp=next(x for x in data["employees"] if x["name"]=="Tamara Vzorová")
    leave=next(x for x in emp["days"] if x["day"]=="2026-11-12")
    assert leave["meal_ticket_eligible"] is False

def test_travel_private_data_requires_login(client):
    for url in ("/api/travel","/api/meals/month?year=2026&month=11",
                "/api/travel/summary.csv"):
        assert client.get(url).status_code==401
