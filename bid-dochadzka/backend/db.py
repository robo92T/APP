"""Databáza dochádzkového systému BID a.s.

Jednoduché riešenie: SQLite (jeden súbor). Pre ostrú prevádzku s väčším
počtom používateľov je možné prejsť na PostgreSQL – SQL príkazy sú písané
štandardne.
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("BID_DB", os.path.join(os.path.dirname(__file__), "..", "data", "dochadzka.db"))

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Organizačná štruktúra: strom (riaditeľ -> úseky -> odbory -> oddelenia -> ...)
CREATE TABLE IF NOT EXISTS org_units (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    short TEXT,
    kind TEXT NOT NULL DEFAULT 'oddelenie',   -- spolocnost / riaditel / usek / odbor / oddelenie / dispecing
    parent_id INTEGER REFERENCES org_units(id) ON DELETE RESTRICT,
    manager_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    deputy_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    cost_center TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

-- Pracovné režimy (rozvrhy pracovného času)
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- fixed (pevný) / flex (pružný) / shift (zmenový, 24/7)
    weekly_hours REAL NOT NULL DEFAULT 37.5,
    params TEXT NOT NULL DEFAULT '{}',  -- JSON (pozri calc.py)
    active INTEGER NOT NULL DEFAULT 1
);

-- Typy zmien pre zmenový režim (napr. D = denná 06-18, N = nočná 18-06)
CREATE TABLE IF NOT EXISTS shift_types (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    start TEXT,                 -- HH:MM, NULL = voľno
    end TEXT,                   -- HH:MM (môže byť "cez polnoc")
    break_min INTEGER NOT NULL DEFAULT 30,
    break_paid INTEGER NOT NULL DEFAULT 0,  -- § 91 ods. 5 ZP – prestávka bez prerušenia práce
    color TEXT NOT NULL DEFAULT '#0b2d5b'
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY,
    personal_number TEXT UNIQUE NOT NULL,   -- osobné číslo (väzba na mzdový systém)
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    title TEXT,
    email TEXT,
    phone TEXT,
    position TEXT,
    org_unit_id INTEGER REFERENCES org_units(id),
    manager_id INTEGER REFERENCES employees(id) ON DELETE SET NULL, -- výnimočný priamy nadriadený
    schedule_id INTEGER REFERENCES schedules(id),
    fte REAL NOT NULL DEFAULT 1.0,          -- úväzok (1.0 = plný, 0.5 = polovičný)
    vacation_days REAL NOT NULL DEFAULT 25, -- ročný nárok
    vacation_carry REAL NOT NULL DEFAULT 0, -- prenesená z min. roka
    chip_uid TEXT UNIQUE,                   -- UID čipu (normalizované HEX)
    allow_remote INTEGER NOT NULL DEFAULT 0,-- smie zaznamenávať príchod/odchod z mobilu/webu
    start_date TEXT,
    end_date TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER UNIQUE REFERENCES employees(id) ON DELETE CASCADE,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    roles TEXT NOT NULL DEFAULT 'zamestnanec',  -- čiarkou: admin,personalista,veduci,dispecer,zamestnanec
    totp_secret TEXT,
    must_change_pw INTEGER NOT NULL DEFAULT 1,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created TEXT NOT NULL,
    expires TEXT NOT NULL,
    ip TEXT
);

-- Typy dôvodov / neprítomností
CREATE TABLE IF NOT EXISTS absence_types (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    counts_as TEXT NOT NULL,           -- work (odpracované) / paid (platená neprítomnosť) / unpaid / break
    kiosk INTEGER NOT NULL DEFAULT 0,  -- zobraziť ako tlačidlo na termináli (krátkodobý odchod)
    request INTEGER NOT NULL DEFAULT 0,-- dá sa žiadať cez žiadosť
    needs_approval INTEGER NOT NULL DEFAULT 1,
    uses_vacation INTEGER NOT NULL DEFAULT 0,
    payroll_code TEXT,                 -- kód pre mzdový systém
    color TEXT NOT NULL DEFAULT '#6b7a90',
    icon TEXT NOT NULL DEFAULT '•',
    sort INTEGER NOT NULL DEFAULT 50
);

-- Záznamy z terminálu / webu / mobilu: IN = príchod, OUT = odchod (s dôvodom)
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    ts TEXT NOT NULL,                  -- lokálny čas YYYY-MM-DDTHH:MM:SS
    kind TEXT NOT NULL,                -- IN / OUT
    reason TEXT REFERENCES absence_types(code), -- pri OUT: NULL = koniec práce, inak dôvod
    source TEXT NOT NULL,              -- kiosk / web / mobile / manual / import
    device_id INTEGER REFERENCES devices(id),
    note TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_events_emp_ts ON events(employee_id, ts);

-- Plán zmien (rozpis služieb) pre 24/7 dispečing
CREATE TABLE IF NOT EXISTS roster (
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    day TEXT NOT NULL,
    shift_code TEXT NOT NULL REFERENCES shift_types(code),
    PRIMARY KEY (employee_id, day)
);

-- Žiadosti (dovolenka, lekár, PN, OČR, náhradné voľno, služobná cesta...)
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    type_code TEXT NOT NULL REFERENCES absence_types(code),
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    half_day INTEGER NOT NULL DEFAULT 0,
    time_from TEXT,                    -- pre hodinové žiadosti (lekár)
    time_to TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending / approved / rejected / cancelled
    approver_id INTEGER REFERENCES employees(id),
    decided_by INTEGER REFERENCES users(id),
    decided_at TEXT,
    decision_note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS holidays (
    day TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    day_off INTEGER NOT NULL DEFAULT 1,     -- deň pracovného pokoja (znižuje fond)
    surcharge INTEGER NOT NULL DEFAULT 1    -- sviatok na účely mzdového zvýhodnenia
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT,
    key_hash TEXT NOT NULL,
    allowed_ip TEXT,
    last_seen TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS month_locks (
    month TEXT PRIMARY KEY,           -- YYYY-MM
    locked_by INTEGER REFERENCES users(id),
    locked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS export_profiles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    fmt TEXT NOT NULL,                 -- csv / xlsx / xml / json
    level TEXT NOT NULL DEFAULT 'month', -- month (súhrn na zamestnanca) / day (denné riadky) / absence (riadky neprítomností)
    delimiter TEXT NOT NULL DEFAULT ';',
    encoding TEXT NOT NULL DEFAULT 'utf-8-sig',
    decimal TEXT NOT NULL DEFAULT ',',
    columns TEXT NOT NULL              -- JSON zoznam [ {"field": "...", "header": "..."} ]
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    user_id INTEGER,
    action TEXT NOT NULL,
    entity TEXT,
    entity_id TEXT,
    detail TEXT,
    ip TEXT
);
"""


def connect():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


@contextmanager
def tx():
    con = connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def rows(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def row(con, sql, params=()):
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


# ---------- heslá (scrypt zo štandardnej knižnice) ----------
def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + salt.hex() + "$" + h.hex()


def check_password(pw: str, stored: str) -> bool:
    try:
        _, salt_hex, h_hex = stored.split("$")
        h = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def init_db():
    con = connect()
    con.executescript(SCHEMA)
    con.commit()
    con.close()


def get_setting(con, key, default=None):
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_setting(con, key, value):
    con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)))
