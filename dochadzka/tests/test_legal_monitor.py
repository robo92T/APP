"""Legislative alerts are informational until an admin explicitly approves a rule."""
from datetime import date
import os
import pytest
from fastapi.testclient import TestClient
import legal_monitor

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
    return {"Authorization":"Bearer "+response.json()["access_token"]}

def test_public_source_parser_drops_scripts_and_nav():
    html='<html><body><nav>ignore navigation</nav><main><h1>Zákonník práce</h1><p>§ 141 prekážka v práci.</p><script>doNotExecute()</script></main></body></html>'
    result=legal_monitor.normalize_html(html)
    assert "Zákonník práce" in result
    assert "doNotExecute" not in result
    assert "ignore navigation" not in result

def test_observation_never_changes_rule_until_admin_approval(client,admin_headers,monkeypatch):
    version={"text":"Zákonník práce – úvodná oficiálna kontrolovaná verzia "*8}
    monkeypatch.setattr(legal_monitor,"fetch_official",lambda source:version["text"])
    first=client.post("/api/legal-monitor/check",headers=admin_headers)
    assert first.status_code==200,first.text
    assert first.json()["changes"]==0
    before=client.get("/api/legal-monitor/rules",headers=admin_headers).json()
    assert next(x for x in before if x["key"]=="doctor_paid_days")["active_value"]==7

    version["text"]="Nová verzia s vecnou legislatívnou informáciou pre kontrolu HR "*8
    changed=client.post("/api/legal-monitor/check",headers=admin_headers)
    assert changed.status_code==200,changed.text
    assert changed.json()["changes"]>=1
    still=client.get("/api/legal-monitor/rules",headers=admin_headers).json()
    assert next(x for x in still if x["key"]=="doctor_paid_days")["active_value"]==7
    notice=client.get("/api/legal-monitor/notices",headers=admin_headers).json()[0]
    assert notice["status"]=="new"
    draft=client.post("/api/legal-monitor/proposals",headers=admin_headers,json={
        "notice_id":notice["id"],"rule_key":"doctor_paid_days","new_value":8,
        "effective_date":"2026-01-01",
        "rationale":"Fiktívna testovacia právna zmena, slúži výhradne na test schvaľovacieho toku."
    })
    assert draft.status_code==201,draft.text
    proposal_id=draft.json()["id"]
    pending=client.get("/api/legal-monitor/rules",headers=admin_headers).json()
    assert next(x for x in pending if x["key"]=="doctor_paid_days")["active_value"]==7
    approval=client.post(f"/api/legal-monitor/proposals/{proposal_id}/approve",
        headers=admin_headers,json={"justification":"Testovací právnik potvrdil účinnosť iba v testovacom režime."})
    assert approval.status_code==200,approval.text
    after=client.get("/api/legal-monitor/rules",headers=admin_headers).json()
    assert next(x for x in after if x["key"]=="doctor_paid_days")["active_value"]==8
    history=client.get("/api/legal-monitor/history",headers=admin_headers).json()
    assert any(v["key"]=="doctor_paid_days" and v["value"]==8 for v in history)

    rollback=client.post(f"/api/legal-monitor/history/{history[0]['id']}/rollback",
        headers=admin_headers,json={"justification":"Zrušenie fiktívnej úpravy po automatickom integračnom teste."})
    assert rollback.status_code==200,rollback.text
    after_rollback=client.get("/api/legal-monitor/rules",headers=admin_headers).json()
    assert next(x for x in after_rollback if x["key"]=="doctor_paid_days")["active_value"]==7

def test_no_admin_token_is_denied(client):
    assert client.post("/api/legal-monitor/check").status_code==401
    assert client.get("/api/legal-monitor/rules").status_code==401
