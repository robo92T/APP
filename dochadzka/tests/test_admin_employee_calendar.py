"""Shared calendar respects roles and computes the same worked-day totals as self-service."""
import os
from fastapi.testclient import TestClient
from main import app


def test_administrator_month_calendar_and_employee_isolation():
    with TestClient(app) as c:
        unauthorized=c.get("/api/admin/employee-calendar/1?year=2026&month=11")
        assert unauthorized.status_code==401

        admin_login=c.post("/api/auth/login",json={
            "username":os.environ["BOOTSTRAP_ADMIN_USERNAME"],
            "password":os.environ["BOOTSTRAP_ADMIN_PASSWORD"]
        })
        assert admin_login.status_code==200,admin_login.text
        headers={"Authorization":"Bearer "+admin_login.json()["access_token"]}
        people=c.get("/api/employees",headers=headers)
        assert people.status_code==200,people.text
        assert people.json()
        employee=people.json()[0]
        employee_id=employee["id"]
        url=f"/api/admin/employee-calendar/{employee_id}?year=2026&month=11"
        result=c.get(url,headers=headers)
        assert result.status_code==200,result.text
        body=result.json()
        assert body["employee_id"]==employee_id
        assert body["employee_name"]==employee["name"]
        assert len(body["rows"])==30
        assert all(x["day"].startswith("2026-11-") for x in body["rows"])
        assert "worked_minutes" in body["rows"][0]
        assert "break_minutes" in body["rows"][0]
        assert "planned_minutes" in body["rows"][0]
        assert all(x["day"].startswith("2026-11-") for x in body["events"])
        assert body["total_worked_minutes"]==sum(x["worked_minutes"] for x in body["rows"])
        assert c.get("/api/admin/employee-calendar/999999?year=2026&month=11",headers=headers).status_code==404
        assert c.get(f"/api/admin/employee-calendar/{employee_id}?year=2026&month=13",headers=headers).status_code==422

        account=c.post(f"/api/auth/accounts?role=employee&employee_id={employee_id}",
            json={"username":"test.calendar.employee.2026","password":"TestCalendarUser2026!"},
            headers=headers)
        assert account.status_code in (200,201),account.text
        employee_login=c.post("/api/auth/login",json={
            "username":"test.calendar.employee.2026","password":"TestCalendarUser2026!"
        })
        assert employee_login.status_code==200,employee_login.text
        own={"Authorization":"Bearer "+employee_login.json()["access_token"]}
        assert c.get(url,headers=own).status_code==403
        # The HR-created account has a temporary password, which must be changed.
        change=c.post("/api/auth/password",headers=own,json={
            "old_password":"TestCalendarUser2026!",
            "new_password":"CalendarUserChanged2026!"
        })
        assert change.status_code==200,change.text
        assert c.get(url,headers=own).status_code==403
        self_calendar=c.get("/api/me/calendar?year=2026&month=11",headers=own)
        assert self_calendar.status_code==200,self_calendar.text
        assert all(x["day"].startswith("2026-11-") for x in self_calendar.json()["events"])
