"""Fictitious demo account can submit own leave and find it in requested month."""
import os
from fastapi.testclient import TestClient
from main import app


def test_demo_employee_is_linked_and_can_submit_leave():
    with TestClient(app) as client:
        username="demo.zamestnanec"
        login=client.post("/api/auth/login",json={
            "username":username,
            "password":os.environ["DEMO_EMPLOYEE_PASSWORD"]
        })
        assert login.status_code==200,login.text
        info=login.json()
        assert info["role"]=="employee"
        assert isinstance(info["employee_id"],int)
        assert info["employee_id"]>0
        assert info["must_change_password"] is False
        headers={"Authorization":"Bearer "+info["access_token"]}
        own=client.get("/api/auth/me",headers=headers)
        assert own.status_code==200,own.text
        assert own.json()["employee_id"]==info["employee_id"]

        summary=client.get("/api/me/summary",headers=headers)
        assert summary.status_code==200,summary.text
        assert summary.json()["name"]=="Filip Ukážkový"
        payload={"kind":"vacation","start":"2026-12-04","end":"2026-12-04",
                 "minutes":None,"note":"Fiktívny test žiadosti cez mobil"}
        submitted=client.post("/api/me/absences",headers=headers,json=payload)
        assert submitted.status_code==201,submitted.text
        created=submitted.json()
        assert created["status"]=="pending"
        month=client.get("/api/me/calendar?year=2026&month=12",headers=headers)
        assert month.status_code==200,month.text
        requests=month.json()["absences"]
        assert any(a["id"]==created["id"] and a["kind"]=="vacation"
                   and a["start"]=="2026-12-04"
                   and a["status"]=="pending" for a in requests)
        forbidden=client.get(
            "/api/admin/employee-calendar/"+str(info["employee_id"])+"?year=2026&month=12",
            headers=headers)
        assert forbidden.status_code==403
