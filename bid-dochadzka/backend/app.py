"""BID Dochádzka – serverová časť (REST API + statické súbory aplikácie).

Spustenie (vývoj):  uvicorn backend.app:app --reload --port 8000
Dokumentácia API:   http://localhost:8000/api/docs
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import struct
import time as _time
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import calc, db, exports, seed

FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    with db.tx() as con:
        pw = seed.base(con)
        if pw:
            print(f"*** Vytvorený admin, heslo: {pw} ***")
    yield


app = FastAPI(title="BID Dochádzka API", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'")
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def client_ip(request: Request):
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "").split(",")[0].strip()


def audit(con, user, action, entity=None, entity_id=None, detail=None, ip=None):
    con.execute("INSERT INTO audit_log(ts,user_id,action,entity,entity_id,detail,ip) VALUES (?,?,?,?,?,?,?)",
                (now_iso(), user["id"] if user else None, action, entity, str(entity_id) if entity_id is not None else None,
                 json.dumps(detail, ensure_ascii=False) if detail is not None else None, ip))


# ------------------------------------------------------------------ TOTP (2FA)
def totp_now(secret_b32: str, t=None, step=30):
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    counter = int((t or _time.time()) // step)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"


def totp_ok(secret, code):
    if not code:
        return False
    t = _time.time()
    return any(hmac.compare_digest(totp_now(secret, t + d * 30), code.strip()) for d in (-1, 0, 1))


# ------------------------------------------------------------------ auth
def current_user(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Neprihlásený")
    token = authorization[7:]
    con = db.connect()
    try:
        s = db.row(con, "SELECT * FROM sessions WHERE token_hash=?", (db.sha256(token),))
        if not s or s["expires"] < now_iso():
            raise HTTPException(401, "Relácia vypršala")
        u = db.row(con, "SELECT * FROM users WHERE id=? AND active=1", (s["user_id"],))
        if not u:
            raise HTTPException(401, "Neplatný používateľ")
        u["roles"] = set(r.strip() for r in u["roles"].split(",") if r.strip())
        u["emp"] = db.row(con, "SELECT * FROM employees WHERE id=?", (u["employee_id"],)) if u["employee_id"] else None
        return u
    finally:
        con.close()


def need(user, *roles):
    if "admin" in user["roles"]:
        return
    if not user["roles"] & set(roles):
        raise HTTPException(403, "Nedostatočné oprávnenie")


def unit_tree(con):
    units = db.rows(con, "SELECT * FROM org_units")
    children = defaultdict(list)
    for u in units:
        children[u["parent_id"]].append(u["id"])
    return {u["id"]: u for u in units}, children


def subtree(children, uid):
    out, stack = set(), [uid]
    while stack:
        x = stack.pop()
        if x in out:
            continue
        out.add(x)
        stack.extend(children.get(x, []))
    return out


def scope_employee_ids(con, user):
    """Zamestnanci, ktorých používateľ vidí: admin/personalista všetkých, vedúci svoj podstrom."""
    if user["roles"] & {"admin", "personalista"}:
        return {r["id"] for r in db.rows(con, "SELECT id FROM employees")}
    ids = set()
    if user["emp"]:
        ids.add(user["emp"]["id"])
        if "veduci" in user["roles"]:
            units, children = unit_tree(con)
            eid = user["emp"]["id"]
            my_units = [u["id"] for u in units.values() if u["manager_id"] == eid or u["deputy_id"] == eid]
            all_units = set()
            for mu in my_units:
                all_units |= subtree(children, mu)
            if all_units:
                q = ",".join("?" * len(all_units))
                ids |= {r["id"] for r in db.rows(con, f"SELECT id FROM employees WHERE org_unit_id IN ({q})", tuple(all_units))}
            ids |= {r["id"] for r in db.rows(con, "SELECT id FROM employees WHERE manager_id=?", (eid,))}
    return ids


def approvers_for(con, emp):
    """Priamy nadriadený (a zástupca). Ak je zamestnanec vedúcim vlastného útvaru, ide sa o úroveň vyššie."""
    if emp.get("manager_id"):
        return [emp["manager_id"]]
    units, _ = unit_tree(con)
    uid = emp["org_unit_id"]
    while uid:
        u = units.get(uid)
        if not u:
            break
        cand = [x for x in (u["manager_id"], u["deputy_id"]) if x and x != emp["id"]]
        if cand and u["manager_id"] != emp["id"]:
            return cand
        uid = u["parent_id"]
    return []


def can_see(con, user, emp_id):
    if emp_id not in scope_employee_ids(con, user):
        raise HTTPException(403, "Zamestnanec mimo vašej pôsobnosti")


def month_locked(con, day_or_ts: str):
    return bool(db.row(con, "SELECT 1 FROM month_locks WHERE month=?", (day_or_ts[:7],)))


def ensure_unlocked(con, day_or_ts: str):
    if month_locked(con, day_or_ts):
        raise HTTPException(409, f"Mesiac {day_or_ts[:7]} je uzavretý pre mzdy")


@app.post("/api/login")
def login(request: Request, body: dict = Body(...)):
    username = (body.get("username") or "").strip().lower()
    password = body.get("password") or ""
    with db.tx() as con:
        u = db.row(con, "SELECT * FROM users WHERE lower(username)=? AND active=1", (username,))
        ip = client_ip(request)
        if not u:
            _time.sleep(0.5)
            raise HTTPException(401, "Nesprávne meno alebo heslo")
        if u["locked_until"] and u["locked_until"] > now_iso():
            raise HTTPException(423, "Účet je dočasne zablokovaný po opakovaných neúspešných pokusoch")
        if not db.check_password(password, u["password_hash"]):
            fails = u["failed_logins"] + 1
            lock = (datetime.now() + timedelta(minutes=15)).isoformat(timespec="seconds") if fails >= 5 else None
            con.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?", (0 if lock else fails, lock, u["id"]))
            audit(con, None, "login_fail", "user", u["id"], ip=ip)
            con.commit()  # neúspešný pokus sa musí uložiť aj keď vraciame chybu
            raise HTTPException(401, "Nesprávne meno alebo heslo")
        roles = set(u["roles"].split(","))
        need_totp = set(db.get_setting(con, "require_totp_roles", [])) & roles
        if u["totp_secret"]:
            if not totp_ok(u["totp_secret"], body.get("totp")):
                if body.get("totp"):
                    audit(con, None, "totp_fail", "user", u["id"], ip=ip)
                return JSONResponse({"totp_required": True, "detail": "Zadajte kód z autentifikačnej aplikácie"}, status_code=401)
        con.execute("UPDATE users SET failed_logins=0, locked_until=NULL WHERE id=?", (u["id"],))
        token = secrets.token_urlsafe(32)
        hours_valid = db.get_setting(con, "session_hours", 10)
        con.execute("INSERT INTO sessions VALUES (?,?,?,?,?)",
                    (db.sha256(token), u["id"], now_iso(), (datetime.now() + timedelta(hours=hours_valid)).isoformat(timespec="seconds"), ip))
        con.execute("DELETE FROM sessions WHERE expires < ?", (now_iso(),))
        audit(con, u, "login", "user", u["id"], ip=ip)
        return {"token": token, "must_change_pw": bool(u["must_change_pw"]),
                "totp_setup_required": bool(need_totp and not u["totp_secret"])}


@app.post("/api/logout")
def logout(authorization: str = Header(default="")):
    if authorization.startswith("Bearer "):
        with db.tx() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (db.sha256(authorization[7:]),))
    return {"ok": True}


def password_policy(pw):
    if len(pw) < 10 or not re.search(r"[A-Za-zÁ-ž]", pw) or not re.search(r"\d", pw):
        raise HTTPException(400, "Heslo musí mať aspoň 10 znakov, písmeno a číslicu")


@app.post("/api/me/password")
def change_password(body: dict = Body(...), user=Depends(current_user)):
    with db.tx() as con:
        u = db.row(con, "SELECT * FROM users WHERE id=?", (user["id"],))
        if not db.check_password(body.get("old") or "", u["password_hash"]):
            raise HTTPException(400, "Pôvodné heslo nesedí")
        password_policy(body.get("new") or "")
        con.execute("UPDATE users SET password_hash=?, must_change_pw=0 WHERE id=?", (db.hash_password(body["new"]), user["id"]))
        audit(con, user, "password_change", "user", user["id"])
    return {"ok": True}


@app.post("/api/me/totp/start")
def totp_start(user=Depends(current_user)):
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    label = f"BID Dochádzka:{user['username']}"
    return {"secret": secret, "uri": f"otpauth://totp/{label}?secret={secret}&issuer=BID%20Dochadzka"}


@app.post("/api/me/totp/confirm")
def totp_confirm(body: dict = Body(...), user=Depends(current_user)):
    if not totp_ok(body.get("secret", ""), body.get("code")):
        raise HTTPException(400, "Kód nesedí – skontrolujte čas v telefóne")
    with db.tx() as con:
        con.execute("UPDATE users SET totp_secret=? WHERE id=?", (body["secret"], user["id"]))
        audit(con, user, "totp_enable", "user", user["id"])
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(current_user)):
    con = db.connect()
    try:
        emp = user["emp"]
        unit = db.row(con, "SELECT * FROM org_units WHERE id=?", (emp["org_unit_id"],)) if emp else None
        approvers = []
        if emp:
            for aid in approvers_for(con, emp):
                a = db.row(con, "SELECT id, first_name, last_name FROM employees WHERE id=?", (aid,))
                if a:
                    approvers.append(a)
        return {"id": user["id"], "username": user["username"], "roles": sorted(user["roles"]),
                "employee": emp, "unit": unit, "approvers": approvers, "totp": bool(user["totp_secret"]),
                "company": db.get_setting(con, "company", "BID a.s.")}
    finally:
        con.close()


# ------------------------------------------------------------------ číselníky
@app.get("/api/meta")
def meta(user=Depends(current_user)):
    con = db.connect()
    try:
        return {
            "absence_types": db.rows(con, "SELECT * FROM absence_types ORDER BY sort"),
            "shift_types": db.rows(con, "SELECT * FROM shift_types ORDER BY code"),
            "schedules": [dict(s, params=json.loads(s["params"])) for s in db.rows(con, "SELECT * FROM schedules ORDER BY id")],
            "units": db.rows(con, "SELECT * FROM org_units ORDER BY id"),
        }
    finally:
        con.close()


def load_context(con, month):
    types = {t["code"]: t for t in db.rows(con, "SELECT * FROM absence_types")}
    shift_types = {s["code"]: s for s in db.rows(con, "SELECT * FROM shift_types")}
    y, m = map(int, month.split("-"))
    holidays = {h["day"]: h for h in db.rows(con, "SELECT * FROM holidays WHERE day LIKE ?", (f"{y:04d}-%",))}
    settings = {"auto_break": db.get_setting(con, "auto_break", True), "min_rest_h": db.get_setting(con, "min_rest_h", 12)}
    schedules = {s["id"]: dict(s, params=json.loads(s["params"])) for s in db.rows(con, "SELECT * FROM schedules")}
    return types, shift_types, holidays, settings, schedules


def compute_for(con, emp, month, ctx=None, now=None):
    types, shift_types, holidays, settings, schedules = ctx or load_context(con, month)
    days = calc.month_days(month)
    lo = (days[0] - timedelta(days=2)).isoformat()
    hi = (days[-1] + timedelta(days=2)).isoformat()
    events = db.rows(con, "SELECT * FROM events WHERE employee_id=? AND deleted=0 AND ts>=? AND ts<? ORDER BY ts",
                     (emp["id"], lo, hi))
    reqs = db.rows(con, "SELECT * FROM requests WHERE employee_id=? AND status='approved' AND date_to>=? AND date_from<=?",
                   (emp["id"], days[0].isoformat(), days[-1].isoformat()))
    roster = {r["day"]: r["shift_code"] for r in db.rows(con, "SELECT * FROM roster WHERE employee_id=? AND day BETWEEN ? AND ?",
                                                         (emp["id"], (days[0] - timedelta(days=1)).isoformat(), days[-1].isoformat()))}
    sched = schedules.get(emp["schedule_id"])
    # sviatky aj z nasledujúceho roka nie sú potrebné – mesiac je v rámci roka
    return calc.compute_month(month, emp, sched, events, reqs, roster, shift_types, holidays, types, settings, now=now)


def vacation_balance(con, emp, year):
    types = {t["code"]: t for t in db.rows(con, "SELECT * FROM absence_types WHERE uses_vacation=1")}
    if not types:
        return {}
    taken = pending = 0.0
    reqs = db.rows(con, f"SELECT * FROM requests WHERE employee_id=? AND type_code IN ({','.join('?'*len(types))}) AND status IN ('approved','pending') AND date_from<=? AND date_to>=?",
                   (emp["id"], *types.keys(), f"{year}-12-31", f"{year}-01-01"))
    if reqs:
        months = set()
        for r in reqs:
            d0, d1 = date.fromisoformat(r["date_from"]), date.fromisoformat(r["date_to"])
            cur = d0
            while cur <= d1:
                if cur.year == year:
                    months.add(cur.strftime("%Y-%m"))
                cur += timedelta(days=1)
        for month in sorted(months):
            ctx = load_context(con, month)
            res_appr = compute_for(con, emp, month, ctx)
            taken += res_appr["summary"].get("vacation_days", 0)
            # pending – spočítame "nanečisto"
            types_all, shift_types, holidays, settings, schedules = ctx
            pend = [dict(r, status="approved") for r in reqs if r["status"] == "pending"]
            if pend:
                days = calc.month_days(month)
                roster = {x["day"]: x["shift_code"] for x in db.rows(con, "SELECT * FROM roster WHERE employee_id=? AND day BETWEEN ? AND ?",
                                                                     (emp["id"], days[0].isoformat(), days[-1].isoformat()))}
                r2 = calc.compute_month(month, emp, schedules.get(emp["schedule_id"]), [], pend, roster, shift_types, holidays, types_all, settings)
                pending += r2["summary"].get("vacation_days", 0)
    total = float(emp["vacation_days"]) + float(emp["vacation_carry"])
    return {"year": year, "entitlement": emp["vacation_days"], "carry": emp["vacation_carry"], "total": total,
            "taken": taken, "pending": pending, "left": total - taken, "left_after_pending": total - taken - pending}


def current_state(con, emp_id):
    last = db.row(con, "SELECT * FROM events WHERE employee_id=? AND deleted=0 ORDER BY ts DESC LIMIT 1", (emp_id,))
    if not last:
        return {"state": "out", "reason": None, "since": None}
    if last["kind"] == "IN":
        return {"state": "in", "reason": None, "since": last["ts"]}
    return {"state": "away" if last["reason"] else "out", "reason": last["reason"], "since": last["ts"]}


# ------------------------------------------------------------------ dochádzka
@app.get("/api/attendance/{emp_id}")
def attendance(emp_id: int, month: str, user=Depends(current_user)):
    con = db.connect()
    try:
        can_see(con, user, emp_id)
        emp = db.row(con, "SELECT * FROM employees WHERE id=?", (emp_id,))
        if not emp:
            raise HTTPException(404)
        res = compute_for(con, emp, month)
        res["employee"] = emp
        res["locked"] = month_locked(con, month)
        res["vacation"] = vacation_balance(con, emp, int(month[:4]))
        res["state"] = current_state(con, emp_id)
        res["events"] = db.rows(con, "SELECT * FROM events WHERE employee_id=? AND ts LIKE ? ORDER BY ts", (emp_id, month + "%"))
        return res
    finally:
        con.close()


@app.post("/api/punch")
def punch(request: Request, body: dict = Body(...), user=Depends(current_user)):
    """Príchod/odchod z webu alebo mobilnej aplikácie (len ak má zamestnanec povolené)."""
    emp = user["emp"]
    if not emp:
        raise HTTPException(400, "Účet nie je prepojený so zamestnancom")
    if not emp["allow_remote"]:
        raise HTTPException(403, "Záznam z mobilu/webu nemáte povolený – použite terminál")
    kind = body.get("kind")
    if kind not in ("IN", "OUT"):
        raise HTTPException(400, "kind musí byť IN alebo OUT")
    with db.tx() as con:
        ts = now_iso()
        ensure_unlocked(con, ts)
        reason = body.get("reason") if kind == "OUT" else None
        con.execute("INSERT INTO events(employee_id,ts,kind,reason,source,note,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (emp["id"], ts, kind, reason, body.get("source", "web")[:10], body.get("note"), user["id"], ts))
        audit(con, user, "punch", "employee", emp["id"], {"kind": kind, "reason": reason}, client_ip(request))
        return {"ok": True, "ts": ts, "state": current_state(con, emp["id"])}


@app.post("/api/events")
def add_event(request: Request, body: dict = Body(...), user=Depends(current_user)):
    """Ručná oprava záznamu vedúcim / personalistom (s povinnou poznámkou)."""
    need(user, "veduci", "personalista")
    emp_id = int(body["employee_id"])
    with db.tx() as con:
        can_see(con, user, emp_id)
        if user["emp"] and emp_id == user["emp"]["id"] and not (user["roles"] & {"admin", "personalista"}):
            raise HTTPException(403, "Vlastnú dochádzku si nemôžete opravovať")
        ts = body["ts"]
        datetime.fromisoformat(ts)
        ensure_unlocked(con, ts)
        if not (body.get("note") or "").strip():
            raise HTTPException(400, "Uveďte dôvod opravy")
        cur = con.execute("INSERT INTO events(employee_id,ts,kind,reason,source,note,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                          (emp_id, ts[:19] if len(ts) >= 19 else ts + ":00", body["kind"], body.get("reason") or None, "manual", body["note"], user["id"], now_iso()))
        audit(con, user, "event_add", "event", cur.lastrowid, body, client_ip(request))
        return {"id": cur.lastrowid}


@app.delete("/api/events/{event_id}")
def delete_event(event_id: int, request: Request, note: str = "", user=Depends(current_user)):
    need(user, "veduci", "personalista")
    with db.tx() as con:
        e = db.row(con, "SELECT * FROM events WHERE id=?", (event_id,))
        if not e:
            raise HTTPException(404)
        can_see(con, user, e["employee_id"])
        ensure_unlocked(con, e["ts"])
        con.execute("UPDATE events SET deleted=1 WHERE id=?", (event_id,))
        audit(con, user, "event_delete", "event", event_id, {"note": note, "event": e}, client_ip(request))
    return {"ok": True}


@app.get("/api/presence")
def presence(user=Depends(current_user)):
    """Kto je teraz v práci (pre vedúcich / dispečing)."""
    need(user, "veduci", "personalista")
    con = db.connect()
    try:
        ids = scope_employee_ids(con, user)
        out = []
        today = date.today().isoformat()
        for e in db.rows(con, "SELECT e.*, u.name AS unit_name FROM employees e LEFT JOIN org_units u ON u.id=e.org_unit_id WHERE e.active=1 ORDER BY e.last_name"):
            if e["id"] not in ids:
                continue
            st = current_state(con, e["id"])
            absent = db.row(con, "SELECT type_code FROM requests WHERE employee_id=? AND status='approved' AND date_from<=? AND date_to>=?",
                            (e["id"], today, today))
            shift = db.row(con, "SELECT shift_code FROM roster WHERE employee_id=? AND day=?", (e["id"], today))
            out.append({"id": e["id"], "name": f"{e['last_name']} {e['first_name']}", "unit": e["unit_name"],
                        "position": e["position"], **st, "absence": absent["type_code"] if absent else None,
                        "shift": shift["shift_code"] if shift else None})
        return out
    finally:
        con.close()


# ------------------------------------------------------------------ žiadosti
@app.get("/api/requests")
def list_requests(scope: str = "mine", status: str = "", user=Depends(current_user)):
    con = db.connect()
    try:
        q = ("SELECT r.*, e.first_name, e.last_name, e.personal_number, t.name AS type_name, t.color, t.icon "
             "FROM requests r JOIN employees e ON e.id=r.employee_id JOIN absence_types t ON t.code=r.type_code ")
        if scope == "mine":
            if not user["emp"]:
                return []
            res = db.rows(con, q + "WHERE r.employee_id=? ORDER BY r.date_from DESC", (user["emp"]["id"],))
        elif scope == "approve":
            # žiadosti, ktoré mám schváliť ja (alebo personalista/admin – všetky čakajúce)
            res = []
            for r in db.rows(con, q + "WHERE r.status='pending' ORDER BY r.date_from"):
                emp = db.row(con, "SELECT * FROM employees WHERE id=?", (r["employee_id"],))
                appr = approvers_for(con, emp)
                if (user["emp"] and user["emp"]["id"] in appr) or (user["roles"] & {"admin"}):
                    if user["emp"] and user["emp"]["id"] == r["employee_id"]:
                        continue
                    res.append(r)
        else:  # team
            ids = scope_employee_ids(con, user)
            res = [r for r in db.rows(con, q + "ORDER BY r.date_from DESC LIMIT 500") if r["employee_id"] in ids]
        if status:
            res = [r for r in res if r["status"] == status]
        return res
    finally:
        con.close()


@app.post("/api/requests")
def create_request(request: Request, body: dict = Body(...), user=Depends(current_user)):
    with db.tx() as con:
        emp_id = int(body.get("employee_id") or (user["emp"]["id"] if user["emp"] else 0))
        if not emp_id:
            raise HTTPException(400, "Chýba zamestnanec")
        if not user["emp"] or emp_id != user["emp"]["id"]:
            need(user, "personalista", "veduci")
            can_see(con, user, emp_id)
        t = db.row(con, "SELECT * FROM absence_types WHERE code=?", (body["type_code"],))
        if not t or not t["request"]:
            raise HTTPException(400, "Neplatný druh žiadosti")
        df, dt = body["date_from"], body.get("date_to") or body["date_from"]
        if date.fromisoformat(dt) < date.fromisoformat(df):
            raise HTTPException(400, "Dátum do je skôr ako dátum od")
        ensure_unlocked(con, df)
        overlap = db.row(con, "SELECT id FROM requests WHERE employee_id=? AND status IN ('pending','approved') AND date_from<=? AND date_to>=? AND time_from IS NULL",
                         (emp_id, dt, df))
        if overlap and not body.get("time_from"):
            raise HTTPException(409, "V tomto období už máte inú žiadosť")
        emp = db.row(con, "SELECT * FROM employees WHERE id=?", (emp_id,))
        status = "approved" if not t["needs_approval"] else "pending"
        # PN/OČR sa nahlasujú (oznámenie), neschvaľujú
        appr = approvers_for(con, emp)
        cur = con.execute(
            "INSERT INTO requests(employee_id,type_code,date_from,date_to,half_day,time_from,time_to,note,status,approver_id,created_at,decided_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (emp_id, t["code"], df, dt, 1 if body.get("half_day") else 0, body.get("time_from") or None, body.get("time_to") or None,
             (body.get("note") or "")[:500], status, appr[0] if appr else None, now_iso(), now_iso() if status == "approved" else None))
        audit(con, user, "request_create", "request", cur.lastrowid, body, client_ip(request))
        return {"id": cur.lastrowid, "status": status}


@app.post("/api/requests/{rid}/{action}")
def decide_request(rid: int, action: str, request: Request, body: dict = Body(default={}), user=Depends(current_user)):
    with db.tx() as con:
        r = db.row(con, "SELECT * FROM requests WHERE id=?", (rid,))
        if not r:
            raise HTTPException(404)
        ensure_unlocked(con, r["date_from"])
        if action == "cancel":
            if not (user["emp"] and user["emp"]["id"] == r["employee_id"]) and not (user["roles"] & {"admin", "personalista"}):
                raise HTTPException(403)
            if r["status"] == "approved" and date.fromisoformat(r["date_from"]) <= date.today() and not (user["roles"] & {"admin", "personalista"}):
                raise HTTPException(400, "Prebiehajúcu/minulú schválenú žiadosť zruší personalista")
            con.execute("UPDATE requests SET status='cancelled', decided_at=? WHERE id=?", (now_iso(), rid))
        elif action in ("approve", "reject"):
            if r["status"] != "pending":
                raise HTTPException(400, "Žiadosť už bola vybavená")
            emp = db.row(con, "SELECT * FROM employees WHERE id=?", (r["employee_id"],))
            appr = approvers_for(con, emp)
            if user["emp"] and user["emp"]["id"] == r["employee_id"]:
                raise HTTPException(403, "Vlastnú žiadosť nemôžete schváliť")
            if not ((user["emp"] and user["emp"]["id"] in appr) or "admin" in user["roles"]):
                raise HTTPException(403, "Nie ste schvaľovateľ tejto žiadosti")
            con.execute("UPDATE requests SET status=?, decided_by=?, decided_at=?, decision_note=? WHERE id=?",
                        ("approved" if action == "approve" else "rejected", user["id"], now_iso(), (body or {}).get("note"), rid))
        else:
            raise HTTPException(400)
        audit(con, user, f"request_{action}", "request", rid, body, client_ip(request))
    return {"ok": True}


# ------------------------------------------------------------------ rozpis zmien (24/7)
@app.get("/api/roster")
def get_roster(unit_id: int, month: str, user=Depends(current_user)):
    con = db.connect()
    try:
        units, children = unit_tree(con)
        ids = subtree(children, unit_id)
        scope = scope_employee_ids(con, user)
        q = ",".join("?" * len(ids))
        emps = [e for e in db.rows(con, f"SELECT * FROM employees WHERE org_unit_id IN ({q}) AND active=1 ORDER BY last_name", tuple(ids)) if e["id"] in scope]
        days = calc.month_days(month)
        types, shift_types, holidays, settings, schedules = load_context(con, month)
        out = []
        norm_days = [d for d in days if d.weekday() < 5 and not (holidays.get(d.isoformat()) or {}).get("day_off")]
        for e in emps:
            sch = schedules.get(e["schedule_id"])
            cells = {r["day"]: r["shift_code"] for r in db.rows(con, "SELECT * FROM roster WHERE employee_id=? AND day BETWEEN ? AND ?",
                                                                (e["id"], days[0].isoformat(), days[-1].isoformat()))}
            planned = sum(calc.shift_window(date.fromisoformat(d), shift_types.get(c, {}))[2] for d, c in cells.items())
            norm = (sch["weekly_hours"] * e["fte"] / 5 * len(norm_days)) if sch else 0
            out.append({"employee": e, "cells": cells, "planned_h": round(planned, 2), "norm_h": round(norm, 2),
                        "schedule_kind": sch["kind"] if sch else None})
        return {"month": month, "days": [d.isoformat() for d in days], "rows": out,
                "holidays": {k: v["name"] for k, v in holidays.items()}, "locked": month_locked(con, month)}
    finally:
        con.close()


@app.put("/api/roster")
def put_roster(request: Request, body: dict = Body(...), user=Depends(current_user)):
    need(user, "veduci", "personalista")
    with db.tx() as con:
        scope = scope_employee_ids(con, user)
        n = 0
        for c in body.get("cells", []):
            eid = int(c["employee_id"])
            if eid not in scope:
                raise HTTPException(403)
            ensure_unlocked(con, c["day"])
            if c.get("shift_code"):
                con.execute("INSERT OR REPLACE INTO roster VALUES (?,?,?)", (eid, c["day"], c["shift_code"]))
            else:
                con.execute("DELETE FROM roster WHERE employee_id=? AND day=?", (eid, c["day"]))
            n += 1
        audit(con, user, "roster_update", "roster", None, {"count": n}, client_ip(request))
    return {"ok": True, "count": n}


@app.post("/api/roster/generate")
def gen_roster(request: Request, body: dict = Body(...), user=Depends(current_user)):
    """Vygeneruje rozpis podľa cyklu (napr. D,N,V,V) s posunom pre každého zamestnanca."""
    need(user, "veduci", "personalista")
    pattern = [p.strip() for p in body["pattern"]]
    anchor = date.fromisoformat(body.get("anchor") or "2026-01-01")
    days = calc.month_days(body["month"])
    with db.tx() as con:
        scope = scope_employee_ids(con, user)
        valid = {s["code"] for s in db.rows(con, "SELECT code FROM shift_types")}
        if not set(pattern) <= valid:
            raise HTTPException(400, "Neznámy kód zmeny v cykle")
        for item in body["employees"]:
            eid, off = int(item["employee_id"]), int(item.get("offset", 0))
            if eid not in scope:
                raise HTTPException(403)
            for d in days:
                ensure_unlocked(con, d.isoformat())
                code = pattern[((d - anchor).days + off) % len(pattern)]
                con.execute("INSERT OR REPLACE INTO roster VALUES (?,?,?)", (eid, d.isoformat(), code))
        audit(con, user, "roster_generate", "roster", None, body, client_ip(request))
    return {"ok": True}


# ------------------------------------------------------------------ správa: štruktúra, zamestnanci, účty
@app.get("/api/units")
def units(user=Depends(current_user)):
    con = db.connect()
    try:
        us = db.rows(con, "SELECT u.*, (SELECT COUNT(*) FROM employees e WHERE e.org_unit_id=u.id AND e.active=1) AS headcount FROM org_units u ORDER BY u.id")
        emps = {e["id"]: e for e in db.rows(con, "SELECT id, first_name, last_name FROM employees")}
        for u in us:
            m = emps.get(u["manager_id"])
            d = emps.get(u["deputy_id"])
            u["manager_name"] = f"{m['first_name']} {m['last_name']}" if m else None
            u["deputy_name"] = f"{d['first_name']} {d['last_name']}" if d else None
        return us
    finally:
        con.close()


@app.post("/api/units")
def save_unit(request: Request, body: dict = Body(...), user=Depends(current_user)):
    need(user, "admin", "personalista")
    with db.tx() as con:
        vals = (body["name"], body.get("short"), body.get("kind", "oddelenie"), body.get("parent_id") or None,
                body.get("manager_id") or None, body.get("deputy_id") or None, body.get("cost_center"), 1 if body.get("active", True) else 0)
        if body.get("id"):
            # ochrana proti cyklu v strome
            units_, children = unit_tree(con)
            if body.get("parent_id") and int(body["parent_id"]) in subtree(children, int(body["id"])):
                raise HTTPException(400, "Útvar nemôže byť podriadený sám sebe")
            con.execute("UPDATE org_units SET name=?,short=?,kind=?,parent_id=?,manager_id=?,deputy_id=?,cost_center=?,active=? WHERE id=?",
                        (*vals, body["id"]))
            uid = body["id"]
        else:
            uid = con.execute("INSERT INTO org_units(name,short,kind,parent_id,manager_id,deputy_id,cost_center,active) VALUES (?,?,?,?,?,?,?,?)", vals).lastrowid
        audit(con, user, "unit_save", "unit", uid, body, client_ip(request))
        return {"id": uid}


@app.delete("/api/units/{uid}")
def delete_unit(uid: int, user=Depends(current_user)):
    need(user, "admin", "personalista")
    with db.tx() as con:
        if db.row(con, "SELECT 1 FROM org_units WHERE parent_id=?", (uid,)) or db.row(con, "SELECT 1 FROM employees WHERE org_unit_id=?", (uid,)):
            raise HTTPException(409, "Útvar má podriadené útvary alebo zamestnancov – najprv ich presuňte")
        con.execute("DELETE FROM org_units WHERE id=?", (uid,))
        audit(con, user, "unit_delete", "unit", uid)
    return {"ok": True}


def norm_uid(uid: str | None):
    if not uid:
        return None
    s = re.sub(r"[^0-9A-Fa-f]", "", uid.strip())
    if not s:
        # niektoré čítačky posielajú dekadické číslo
        s = uid.strip()
    return s.upper()


@app.get("/api/employees")
def list_employees(user=Depends(current_user)):
    con = db.connect()
    try:
        ids = scope_employee_ids(con, user)
        res = db.rows(con, "SELECT e.*, u.name AS unit_name, s.name AS schedule_name, us.username, us.roles, us.id AS user_id, us.active AS user_active "
                           "FROM employees e LEFT JOIN org_units u ON u.id=e.org_unit_id LEFT JOIN schedules s ON s.id=e.schedule_id "
                           "LEFT JOIN users us ON us.employee_id=e.id ORDER BY e.last_name, e.first_name")
        return [r for r in res if r["id"] in ids]
    finally:
        con.close()


@app.post("/api/employees")
def save_employee(request: Request, body: dict = Body(...), user=Depends(current_user)):
    need(user, "admin", "personalista")
    f = ["personal_number", "first_name", "last_name", "title", "email", "phone", "position", "org_unit_id", "manager_id",
         "schedule_id", "fte", "vacation_days", "vacation_carry", "chip_uid", "allow_remote", "start_date", "end_date", "active"]
    data = {k: body.get(k) for k in f}
    data["chip_uid"] = norm_uid(data["chip_uid"])
    for k in ("org_unit_id", "manager_id", "schedule_id"):
        data[k] = int(data[k]) if data.get(k) else None
    data["fte"] = float(data.get("fte") or 1)
    if not 0 < data["fte"] <= 1:
        raise HTTPException(400, "Úväzok musí byť v rozsahu 0,01 – 1")
    data["vacation_days"] = float(data.get("vacation_days") or 25)
    data["vacation_carry"] = float(data.get("vacation_carry") or 0)
    data["allow_remote"] = 1 if data.get("allow_remote") else 0
    data["active"] = 0 if data.get("active") in (0, False, "0") else 1
    if not data["personal_number"] or not data["first_name"] or not data["last_name"]:
        raise HTTPException(400, "Osobné číslo, meno a priezvisko sú povinné")
    with db.tx() as con:
        if data["chip_uid"]:
            other = db.row(con, "SELECT id, first_name, last_name FROM employees WHERE chip_uid=? AND id<>?", (data["chip_uid"], body.get("id") or 0))
            if other:
                raise HTTPException(409, f"Čip je už priradený: {other['first_name']} {other['last_name']}")
        if body.get("id"):
            con.execute(f"UPDATE employees SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*[data[k] for k in f], body["id"]))
            eid = body["id"]
        else:
            eid = con.execute(f"INSERT INTO employees({','.join(f)}) VALUES ({','.join('?' * len(f))})", tuple(data[k] for k in f)).lastrowid
        # používateľský účet
        if body.get("username"):
            roles = ",".join(sorted(set(body.get("roles") or ["zamestnanec"])))
            if "admin" in roles and "admin" not in user["roles"]:
                raise HTTPException(403, "Rolu admin môže prideliť len admin")
            u = db.row(con, "SELECT * FROM users WHERE employee_id=?", (eid,))
            if u:
                con.execute("UPDATE users SET username=?, roles=?, active=? WHERE id=?",
                            (body["username"].strip().lower(), roles, 0 if body.get("user_active") in (0, False) else 1, u["id"]))
            else:
                pw = body.get("password") or secrets.token_urlsafe(9)
                con.execute("INSERT INTO users(employee_id,username,password_hash,roles,must_change_pw) VALUES (?,?,?,?,1)",
                            (eid, body["username"].strip().lower(), db.hash_password(pw), roles))
                audit(con, user, "user_create", "employee", eid, {"username": body["username"], "roles": roles}, client_ip(request))
                body["_initial_password"] = pw
        audit(con, user, "employee_save", "employee", eid, {k: data[k] for k in f}, client_ip(request))
        return {"id": eid, "initial_password": body.get("_initial_password")}


@app.post("/api/employees/{eid}/reset-password")
def reset_password(eid: int, request: Request, user=Depends(current_user)):
    need(user, "admin", "personalista")
    pw = secrets.token_urlsafe(9)
    with db.tx() as con:
        u = db.row(con, "SELECT * FROM users WHERE employee_id=?", (eid,))
        if not u:
            raise HTTPException(404, "Zamestnanec nemá účet")
        if "admin" in u["roles"] and "admin" not in user["roles"]:
            raise HTTPException(403)
        con.execute("UPDATE users SET password_hash=?, must_change_pw=1, totp_secret=NULL, failed_logins=0, locked_until=NULL WHERE id=?",
                    (db.hash_password(pw), u["id"]))
        con.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))
        audit(con, user, "password_reset", "employee", eid, ip=client_ip(request))
    return {"password": pw}


@app.post("/api/schedules")
def save_schedule(body: dict = Body(...), user=Depends(current_user)):
    need(user, "admin", "personalista")
    if body.get("kind") not in ("fixed", "flex", "shift"):
        raise HTTPException(400, "Neplatný druh režimu")
    with db.tx() as con:
        vals = (body["name"], body["kind"], float(body.get("weekly_hours") or 37.5), json.dumps(body.get("params") or {}), 1 if body.get("active", True) else 0)
        if body.get("id"):
            con.execute("UPDATE schedules SET name=?,kind=?,weekly_hours=?,params=?,active=? WHERE id=?", (*vals, body["id"]))
            sid = body["id"]
        else:
            sid = con.execute("INSERT INTO schedules(name,kind,weekly_hours,params,active) VALUES (?,?,?,?,?)", vals).lastrowid
        audit(con, user, "schedule_save", "schedule", sid, body)
        return {"id": sid}


@app.post("/api/shift-types")
def save_shift(body: dict = Body(...), user=Depends(current_user)):
    need(user, "admin", "personalista")
    with db.tx() as con:
        con.execute("INSERT OR REPLACE INTO shift_types(code,name,start,end,break_min,break_paid,color) VALUES (?,?,?,?,?,?,?)",
                    (body["code"].upper()[:4], body["name"], body.get("start") or None, body.get("end") or None,
                     int(body.get("break_min") or 0), 1 if body.get("break_paid") else 0, body.get("color") or "#0b2d5b"))
        audit(con, user, "shift_type_save", "shift_type", body["code"], body)
    return {"ok": True}


@app.post("/api/absence-types")
def save_absence_type(body: dict = Body(...), user=Depends(current_user)):
    need(user, "admin", "personalista")
    if body.get("counts_as") not in ("work", "paid", "unpaid", "break"):
        raise HTTPException(400, "counts_as: work/paid/unpaid/break")
    with db.tx() as con:
        con.execute("INSERT OR REPLACE INTO absence_types VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (body["code"].upper()[:10], body["name"], body["counts_as"], 1 if body.get("kiosk") else 0, 1 if body.get("request") else 0,
                     1 if body.get("needs_approval") else 0, 1 if body.get("uses_vacation") else 0, body.get("payroll_code"),
                     body.get("color") or "#6b7a90", body.get("icon") or "•", int(body.get("sort") or 50)))
        audit(con, user, "absence_type_save", "absence_type", body["code"], body)
    return {"ok": True}


@app.get("/api/holidays")
def get_holidays(year: int, user=Depends(current_user)):
    con = db.connect()
    try:
        return db.rows(con, "SELECT * FROM holidays WHERE day LIKE ? ORDER BY day", (f"{year}-%",))
    finally:
        con.close()


@app.post("/api/holidays")
def save_holiday(body: dict = Body(...), user=Depends(current_user)):
    need(user, "admin", "personalista")
    with db.tx() as con:
        if body.get("delete"):
            con.execute("DELETE FROM holidays WHERE day=?", (body["day"],))
        else:
            date.fromisoformat(body["day"])
            con.execute("INSERT OR REPLACE INTO holidays VALUES (?,?,?,?)", (body["day"], body["name"], 1 if body.get("day_off") else 0, 1 if body.get("surcharge") else 0))
        audit(con, user, "holiday_save", "holiday", body["day"], body)
    return {"ok": True}


@app.post("/api/holidays/generate")
def generate_holidays(body: dict = Body(...), user=Depends(current_user)):
    need(user, "admin", "personalista")
    with db.tx() as con:
        for d, n, off, sur in seed.holidays_for(int(body["year"])):
            con.execute("INSERT OR IGNORE INTO holidays VALUES (?,?,?,?)", (d, n, off, sur))
    return {"ok": True}


# ------------------------------------------------------------------ terminály
@app.get("/api/devices")
def devices(user=Depends(current_user)):
    need(user, "admin")
    con = db.connect()
    try:
        return db.rows(con, "SELECT id,name,location,allowed_ip,last_seen,active FROM devices ORDER BY id")
    finally:
        con.close()


@app.post("/api/devices")
def save_device(body: dict = Body(...), user=Depends(current_user)):
    need(user, "admin")
    with db.tx() as con:
        key = None
        if body.get("id"):
            con.execute("UPDATE devices SET name=?, location=?, allowed_ip=?, active=? WHERE id=?",
                        (body["name"], body.get("location"), body.get("allowed_ip") or None, 1 if body.get("active", True) else 0, body["id"]))
            did = body["id"]
            if body.get("rotate_key"):
                key = secrets.token_urlsafe(24)
                con.execute("UPDATE devices SET key_hash=? WHERE id=?", (db.sha256(key), did))
        else:
            key = secrets.token_urlsafe(24)
            did = con.execute("INSERT INTO devices(name,location,key_hash,allowed_ip) VALUES (?,?,?,?)",
                              (body["name"], body.get("location"), db.sha256(key), body.get("allowed_ip") or None)).lastrowid
        audit(con, user, "device_save", "device", did, {"name": body["name"]})
        return {"id": did, "key": key}


def kiosk_device(request: Request, x_device_key: str = Header(default="")):
    con = db.connect()
    try:
        d = db.row(con, "SELECT * FROM devices WHERE key_hash=? AND active=1", (db.sha256(x_device_key),))
        if not d:
            raise HTTPException(401, "Neznámy terminál")
        if d["allowed_ip"] and client_ip(request) not in [x.strip() for x in d["allowed_ip"].split(",")]:
            raise HTTPException(403, "Terminál z nepovolenej adresy")
        con.execute("UPDATE devices SET last_seen=? WHERE id=?", (now_iso(), d["id"]))
        con.commit()
        return d
    finally:
        con.close()


@app.get("/api/kiosk/info")
def kiosk_info(device=Depends(kiosk_device)):
    con = db.connect()
    try:
        return {"device": {"id": device["id"], "name": device["name"], "location": device["location"]},
                "company": db.get_setting(con, "company"),
                "reasons": db.rows(con, "SELECT code,name,icon,color,counts_as FROM absence_types WHERE kiosk=1 ORDER BY sort")}
    finally:
        con.close()


def kiosk_employee(con, uid):
    e = db.row(con, "SELECT * FROM employees WHERE chip_uid=? AND active=1", (norm_uid(uid),))
    if not e:
        raise HTTPException(404, "Neznámy čip – kontaktujte personálne oddelenie")
    return e


@app.post("/api/kiosk/identify")
def kiosk_identify(body: dict = Body(...), device=Depends(kiosk_device)):
    con = db.connect()
    try:
        e = kiosk_employee(con, body.get("uid"))
        st = current_state(con, e["id"])
        today = date.today()
        res = compute_for(con, e, today.strftime("%Y-%m"))
        d = next((x for x in res["days"] if x["day"] == today.isoformat()), None)
        vac = vacation_balance(con, e, today.year)
        shift = db.row(con, "SELECT shift_code FROM roster WHERE employee_id=? AND day=?", (e["id"], today.isoformat()))
        return {"employee": {"name": f"{e['first_name']} {e['last_name']}", "position": e["position"]},
                **st, "today_h": d["worked_h"] if d else 0, "month_balance_h": res["summary"].get("balance_to_date_h", 0),
                "vacation_left": vac.get("left"), "shift": shift["shift_code"] if shift else None,
                "suggest": "OUT" if st["state"] == "in" else "IN"}
    finally:
        con.close()


@app.post("/api/kiosk/punch")
def kiosk_punch(request: Request, body: dict = Body(...), device=Depends(kiosk_device)):
    kind = body.get("kind")
    if kind not in ("IN", "OUT"):
        raise HTTPException(400)
    with db.tx() as con:
        e = kiosk_employee(con, body.get("uid"))
        ts = now_iso()
        note = None
        if body.get("offline_ts"):
            # záznam z výpadku siete – terminál ho uložil lokálne s vlastným časom
            ots = datetime.fromisoformat(body["offline_ts"][:19])
            if not (datetime.now() - timedelta(hours=72) <= ots <= datetime.now() + timedelta(minutes=2)):
                raise HTTPException(400, "Offline záznam je mimo povoleného okna 72 h")
            ts = ots.isoformat(timespec="seconds")
            note = "offline záznam z terminálu"
        ensure_unlocked(con, ts)
        deb = db.get_setting(con, "kiosk_debounce_s", 60)
        last = db.row(con, "SELECT * FROM events WHERE employee_id=? AND deleted=0 AND ts<=? ORDER BY ts DESC LIMIT 1", (e["id"], ts))
        if last and last["kind"] == kind and (datetime.fromisoformat(ts) - datetime.fromisoformat(last["ts"])).total_seconds() < deb:
            return {"ok": True, "duplicate": True, "ts": last["ts"], "name": f"{e['first_name']} {e['last_name']}"}
        reason = body.get("reason") if kind == "OUT" else None
        if reason and not db.row(con, "SELECT 1 FROM absence_types WHERE code=? AND kiosk=1", (reason,)):
            raise HTTPException(400, "Neplatný dôvod")
        con.execute("INSERT INTO events(employee_id,ts,kind,reason,source,device_id,note,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (e["id"], ts, kind, reason, "kiosk", device["id"], note, now_iso()))
        return {"ok": True, "ts": ts, "name": f"{e['first_name']} {e['last_name']}", "kind": kind, "reason": reason}


# ------------------------------------------------------------------ mzdy / exporty
@app.get("/api/report")
def report(month: str, unit_id: int | None = None, user=Depends(current_user)):
    need(user, "veduci", "personalista")
    con = db.connect()
    try:
        results = collect(con, user, month, unit_id)
        out = []
        for emp, unit, res in results:
            out.append({"employee": {k: emp[k] for k in ("id", "personal_number", "first_name", "last_name", "fte", "position")},
                        "unit": unit["name"] if unit else None, "summary": res["summary"]})
        return {"month": month, "locked": month_locked(con, month), "rows": out}
    finally:
        con.close()


def collect(con, user, month, unit_id=None):
    scope = scope_employee_ids(con, user)
    units, children = unit_tree(con)
    allowed_units = subtree(children, unit_id) if unit_id else None
    ctx = load_context(con, month)
    out = []
    first, last = calc.month_days(month)[0].isoformat(), calc.month_days(month)[-1].isoformat()
    for e in db.rows(con, "SELECT * FROM employees ORDER BY last_name, first_name"):
        if e["id"] not in scope:
            continue
        if allowed_units is not None and e["org_unit_id"] not in allowed_units:
            continue
        if e["start_date"] and e["start_date"] > last:
            continue
        if e["end_date"] and e["end_date"] < first:
            continue
        out.append((e, units.get(e["org_unit_id"]), compute_for(con, e, month, ctx)))
    return out


@app.get("/api/export-profiles")
def export_profiles(user=Depends(current_user)):
    need(user, "personalista", "veduci")
    con = db.connect()
    try:
        return [dict(p, columns=json.loads(p["columns"])) for p in db.rows(con, "SELECT * FROM export_profiles ORDER BY id")]
    finally:
        con.close()


@app.post("/api/export-profiles")
def save_export_profile(body: dict = Body(...), user=Depends(current_user)):
    need(user, "personalista")
    if body.get("fmt") not in ("csv", "xlsx", "xml", "json") or body.get("level") not in ("month", "day", "absence"):
        raise HTTPException(400, "Neplatný formát alebo úroveň")
    with db.tx() as con:
        vals = (body["name"], body["fmt"], body["level"], body.get("delimiter") or ";", body.get("encoding") or "utf-8-sig",
                body.get("decimal") or ",", json.dumps(body["columns"], ensure_ascii=False))
        if body.get("id"):
            con.execute("UPDATE export_profiles SET name=?,fmt=?,level=?,delimiter=?,encoding=?,decimal=?,columns=? WHERE id=?", (*vals, body["id"]))
            pid = body["id"]
        else:
            pid = con.execute("INSERT INTO export_profiles(name,fmt,level,delimiter,encoding,decimal,columns) VALUES (?,?,?,?,?,?,?)", vals).lastrowid
        audit(con, user, "export_profile_save", "export_profile", pid, body)
        return {"id": pid}


@app.get("/api/export")
def do_export(month: str, profile_id: int, request: Request, unit_id: int | None = None, user=Depends(current_user)):
    need(user, "personalista")
    con = db.connect()
    try:
        p = db.row(con, "SELECT * FROM export_profiles WHERE id=?", (profile_id,))
        if not p:
            raise HTTPException(404)
        results = collect(con, user, month, unit_id)
        types = {t["code"]: t for t in db.rows(con, "SELECT * FROM absence_types")}
        rows_ = exports.build_rows(p["level"], results, types)
        data, mime, ext = exports.render(p, rows_)
        audit(con, user, "export", "export_profile", profile_id, {"month": month, "unit_id": unit_id, "rows": len(rows_)}, client_ip(request))
        con.commit()
        fname = f"dochadzka_{month}_{re.sub(r'[^A-Za-z0-9]+', '_', p['name'])[:40]}.{ext}"
        return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{fname}"'})
    finally:
        con.close()


@app.post("/api/month-lock")
def lock_month(body: dict = Body(...), user=Depends(current_user)):
    need(user, "personalista")
    month = body["month"]
    with db.tx() as con:
        if body.get("unlock"):
            if "admin" not in user["roles"]:
                raise HTTPException(403, "Odomknúť mesiac môže len admin")
            con.execute("DELETE FROM month_locks WHERE month=?", (month,))
        else:
            con.execute("INSERT OR IGNORE INTO month_locks VALUES (?,?,?)", (month, user["id"], now_iso()))
        audit(con, user, "month_unlock" if body.get("unlock") else "month_lock", "month", month)
    return {"ok": True}


@app.get("/api/audit")
def audit_list(limit: int = 200, user=Depends(current_user)):
    need(user, "admin")
    con = db.connect()
    try:
        return db.rows(con, "SELECT a.*, u.username FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT ?", (min(limit, 2000),))
    finally:
        con.close()


@app.get("/api/settings")
def get_settings(user=Depends(current_user)):
    need(user, "admin")
    con = db.connect()
    try:
        return {r["key"]: json.loads(r["value"]) for r in db.rows(con, "SELECT * FROM settings")}
    finally:
        con.close()


@app.post("/api/settings")
def save_settings(body: dict = Body(...), user=Depends(current_user)):
    need(user, "admin")
    allowed = {"company", "auto_break", "min_rest_h", "kiosk_debounce_s", "require_totp_roles", "session_hours"}
    with db.tx() as con:
        for k, v in body.items():
            if k in allowed:
                db.set_setting(con, k, v)
        audit(con, user, "settings_save", "settings", None, body)
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True, "time": now_iso()}


# ------------------------------------------------------------------ statické súbory (PWA + kiosk)
@app.get("/kiosk")
def kiosk_page():
    return FileResponse(os.path.join(FRONTEND, "kiosk.html"))


@app.get("/")
def index_page():
    return FileResponse(os.path.join(FRONTEND, "index.html"))


@app.get("/sw.js")
def sw():
    return FileResponse(os.path.join(FRONTEND, "sw.js"), media_type="application/javascript")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
