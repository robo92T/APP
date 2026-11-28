"""Regression: editing/punch correction list must not return HTTP 500."""
import os
from fastapi.testclient import TestClient
from main import app

def test_administrator_correction_event_list_and_employee_denial():
    with TestClient(app) as c:
        admin=c.post("/api/auth/login",json={
            "username":os.environ["BOOTSTRAP_ADMIN_USERNAME"],
            "password":os.environ["BOOTSTRAP_ADMIN_PASSWORD"]})
        assert admin.status_code==200,admin.text
        headers={"Authorization":"Bearer "+admin.json()["access_token"]}
        people=c.get("/api/employees",headers=headers)
        assert people.status_code==200,people.text
        emp_id=people.json()[0]["id"]
        url=f"/api/corrections/events?employee_id={emp_id}&start=2026-11-01&end=2026-11-28"
        result=c.get(url,headers=headers)
        assert result.status_code==200,result.text
        worker=c.post("/api/auth/login",json={"username":"demo.zamestnanec",
             "password":os.environ["DEMO_EMPLOYEE_PASSWORD"]})
        assert worker.status_code==200
        employee_headers={"Authorization":"Bearer "+worker.json()["access_token"]}
        assert c.get(url,headers=employee_headers).status_code==403
