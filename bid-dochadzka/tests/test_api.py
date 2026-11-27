"""Integračné testy API nad demo dátami."""
import os
import tempfile

os.environ["BID_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

import pytest
from fastapi.testclient import TestClient

from backend import db, seed

db.init_db()
with db.tx() as _con:
    seed.base(_con, admin_password="Admin2026!")
    seed.demo(_con)

from backend.app import app  # noqa: E402

c = TestClient(app)
KIOSK = {"X-Device-Key": "demo-kiosk-key"}


def login(u, p="Demo2026!"):
    r = c.post("/api/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def emp_id(h):
    return c.get("/api/me", headers=h).json()["employee"]["id"]


def test_login_wrong_password_and_lockout():
    for _ in range(5):
        assert c.post("/api/login", json={"username": "purban", "password": "zle"}).status_code == 401
    assert c.post("/api/login", json={"username": "purban", "password": "Demo2026!"}).status_code == 423


def test_unauthenticated_rejected():
    assert c.get("/api/employees").status_code == 401


def test_employee_sees_only_self():
    h = login("jsimkova")
    ids = {e["id"] for e in c.get("/api/employees", headers=h).json()}
    assert ids == {emp_id(h)}
    other = [e for e in c.get("/api/employees", headers=login("admin", "Admin2026!")).json() if e["last_name"] == "Novák"][0]
    assert c.get(f"/api/attendance/{other['id']}?month=2026-11", headers=h).status_code == 403


def test_manager_scope_subtree():
    h = login("tvarga")  # riaditeľ úseku dopravy
    names = {e["last_name"] for e in c.get("/api/employees", headers=h).json()}
    assert {"Hudák", "Lukáčová", "Molnár"} <= names
    assert "Šimková" not in names


def test_request_flow_and_self_approval_forbidden():
    he = login("klukacova")
    r = c.post("/api/requests", json={"type_code": "DOV", "date_from": "2027-02-01", "date_to": "2027-02-05"}, headers=he)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    rid = r.json()["id"]
    assert c.post(f"/api/requests/{rid}/approve", headers=he).status_code == 403
    hm = login("mpolak")  # vedúci odboru plánovania
    pend = {x["id"] for x in c.get("/api/requests?scope=approve", headers=hm).json()}
    assert rid in pend
    assert c.post(f"/api/requests/{rid}/approve", json={"note": "ok"}, headers=hm).status_code == 200
    mine = [x for x in c.get("/api/requests?scope=mine", headers=he).json() if x["id"] == rid][0]
    assert mine["status"] == "approved"


def test_manager_request_goes_to_upper_level():
    hm = login("mpolak")
    rid = c.post("/api/requests", json={"type_code": "DOV", "date_from": "2027-03-01", "date_to": "2027-03-01"}, headers=hm).json()["id"]
    hv = login("tvarga")
    assert rid in {x["id"] for x in c.get("/api/requests?scope=approve", headers=hv).json()}


def test_overlapping_request_rejected():
    he = login("klukacova")
    assert c.post("/api/requests", json={"type_code": "DOV", "date_from": "2027-02-03", "date_to": "2027-02-04"}, headers=he).status_code == 409


def test_pn_is_notification_without_approval():
    he = login("jkollar")
    r = c.post("/api/requests", json={"type_code": "PN", "date_from": "2027-01-11", "date_to": "2027-01-15"}, headers=he)
    assert r.json()["status"] == "approved"


def test_remote_punch_permission():
    assert c.post("/api/punch", json={"kind": "IN"}, headers=login("ahudak")).status_code == 403  # dispečer – len terminál
    assert c.post("/api/punch", json={"kind": "IN", "source": "mobile"}, headers=login("jsimkova")).status_code == 200


def test_kiosk_identify_and_punch():
    uid = "04A11016B2C3D4"  # demo čip P. Urban
    assert c.post("/api/kiosk/identify", json={"uid": uid}).status_code == 401
    r = c.post("/api/kiosk/identify", json={"uid": uid.lower()}, headers=KIOSK)
    assert r.status_code == 200 and r.json()["employee"]["name"] == "Patrik Urban"
    kind = r.json()["suggest"]
    p = c.post("/api/kiosk/punch", json={"uid": uid, "kind": kind}, headers=KIOSK).json()
    assert p["ok"] and not p.get("duplicate")
    p2 = c.post("/api/kiosk/punch", json={"uid": uid, "kind": kind}, headers=KIOSK).json()
    assert p2.get("duplicate")  # ochrana pred dvojitým priložením
    assert c.post("/api/kiosk/identify", json={"uid": "FFFF"}, headers=KIOSK).status_code == 404


def test_manual_correction_needs_note_and_is_audited():
    hm = login("mpolak")
    eid = [e for e in c.get("/api/employees", headers=hm).json() if e["last_name"] == "Lukáčová"][0]["id"]
    assert c.post("/api/events", json={"employee_id": eid, "ts": "2026-11-26T16:00", "kind": "OUT"}, headers=hm).status_code == 400
    assert c.post("/api/events", json={"employee_id": eid, "ts": "2026-11-26T16:00", "kind": "OUT", "note": "zabudnutý odchod"}, headers=hm).status_code == 200
    ha = login("admin", "Admin2026!")
    assert any(a["action"] == "event_add" for a in c.get("/api/audit", headers=ha).json())


def test_exports_all_profiles():
    h = login("lbalaz")
    for p in c.get("/api/export-profiles", headers=h).json():
        r = c.get(f"/api/export?month=2026-11&profile_id={p['id']}", headers=h)
        assert r.status_code == 200, p["name"]
        assert len(r.content) > 100
    csv = c.get("/api/export?month=2026-11&profile_id=1", headers=h).content.decode("cp1250")
    assert csv.splitlines()[0].startswith("Osobné číslo;Priezvisko")
    assert "Urban" in csv


def test_month_lock_blocks_changes():
    h = login("lbalaz")
    hm = login("mpolak")
    eid = [e for e in c.get("/api/employees", headers=hm).json() if e["last_name"] == "Lukáčová"][0]["id"]
    assert c.post("/api/month-lock", json={"month": "2026-10"}, headers=h).status_code == 200
    r = c.post("/api/events", json={"employee_id": eid, "ts": "2026-10-10T08:00", "kind": "IN", "note": "x"}, headers=hm)
    assert r.status_code == 409
    assert c.post("/api/month-lock", json={"month": "2026-10", "unlock": True}, headers=h).status_code == 403


def test_roster_generate_and_read():
    h = login("rmolnar")
    disp = [u for u in c.get("/api/units", headers=h).json() if u["kind"] == "dispecing"][0]
    emps = [e for e in c.get("/api/employees", headers=h).json() if e["org_unit_id"] == disp["id"] and e["schedule_name"].startswith("Dispe")]
    body = {"month": "2027-01", "pattern": ["D", "N", "V", "V"], "employees": [{"employee_id": e["id"], "offset": i} for i, e in enumerate(emps)]}
    assert c.post("/api/roster/generate", json=body, headers=h).status_code == 200
    r = c.get(f"/api/roster?unit_id={disp['id']}&month=2027-01", headers=h).json()
    row = [x for x in r["rows"] if x["employee"]["id"] == emps[0]["id"]][0]
    assert len(row["cells"]) == 31 and row["planned_h"] > 150


def test_admin_can_build_structure_and_employee_with_chip():
    h = login("admin", "Admin2026!")
    root = [u for u in c.get("/api/units", headers=h).json() if u["parent_id"] is None][0]
    uid = c.post("/api/units", json={"name": "Odbor marketingu", "kind": "odbor", "parent_id": root["id"]}, headers=h).json()["id"]
    r = c.post("/api/employees", json={"personal_number": "2001", "first_name": "Nový", "last_name": "Kolega", "org_unit_id": uid,
                                        "schedule_id": 1, "fte": 0.8, "chip_uid": "de:ad:be:ef", "username": "nkolega", "roles": ["zamestnanec"]}, headers=h)
    assert r.status_code == 200 and r.json()["initial_password"]
    dup = c.post("/api/employees", json={"personal_number": "2002", "first_name": "X", "last_name": "Y", "chip_uid": "DEADBEEF"}, headers=h)
    assert dup.status_code == 409  # rovnaký čip nemôžu mať dvaja
    # cyklus v strome
    assert c.post("/api/units", json={"id": root["id"], "name": root["name"], "parent_id": uid}, headers=h).status_code == 400
