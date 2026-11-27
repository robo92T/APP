"""Počiatočné dáta: číselníky, sviatky, exportné profily a (voliteľne) demo firma.

Spustenie:  python -m backend.seed            (číselníky + admin)
            python -m backend.seed --demo     (aj demo štruktúra a zamestnanci)
"""
import json
import random
import secrets
import sys
from datetime import date, datetime, timedelta

from . import db


def easter(y: int) -> date:
    """Veľkonočná nedeľa (anonymný gregoriánsky algoritmus)."""
    a = y % 19
    b, c = divmod(y, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(y, month, day)


def holidays_for(year: int):
    """Sviatky podľa zákona č. 241/1993 Z. z. v znení zákona č. 261/2025 Z. z.

    - 1. 9., 28. 10., 17. 11. – štátne sviatky, ale nie dni pracovného pokoja ani
      sviatky na účely ZP (§ 2 ods. 3).
    - v roku 2026 nie sú 8. 5. a 15. 9. dňami pracovného pokoja (§ 4b).
      Či sa na ne v r. 2026 vzťahuje mzdové zvýhodnenie za sviatok, OVERTE
      (usmernenie MPSVR SR) – nastavenie 'surcharge' je možné zmeniť v Správe.
    """
    e = easter(year)
    lst = [
        (date(year, 1, 1), "Deň vzniku Slovenskej republiky", 1, 1),
        (date(year, 1, 6), "Zjavenie Pána (Traja králi)", 1, 1),
        (e - timedelta(days=2), "Veľký piatok", 1, 1),
        (e + timedelta(days=1), "Veľkonočný pondelok", 1, 1),
        (date(year, 5, 1), "Sviatok práce", 1, 1),
        (date(year, 5, 8), "Deň víťazstva nad fašizmom", 1, 1),
        (date(year, 7, 5), "Sviatok sv. Cyrila a Metoda", 1, 1),
        (date(year, 8, 29), "Výročie SNP", 1, 1),
        (date(year, 9, 1), "Deň Ústavy SR (nie je deň pracovného pokoja)", 0, 0),
        (date(year, 9, 15), "Sedembolestná Panna Mária", 1, 1),
        (date(year, 10, 28), "Deň vzniku samostatného česko-slovenského štátu (nie je deň pracovného pokoja)", 0, 0),
        (date(year, 11, 1), "Sviatok všetkých svätých", 1, 1),
        (date(year, 11, 17), "Deň boja za slobodu a demokraciu (nie je deň pracovného pokoja)", 0, 0),
        (date(year, 12, 24), "Štedrý deň", 1, 1),
        (date(year, 12, 25), "Prvý sviatok vianočný", 1, 1),
        (date(year, 12, 26), "Druhý sviatok vianočný", 1, 1),
    ]
    out = []
    for d, n, off, sur in lst:
        if year == 2026 and (d.month, d.day) in ((5, 8), (9, 15)):
            off = 0
            n += " (v r. 2026 nie je deň pracovného pokoja – § 4b)"
        out.append((d.isoformat(), n, off, sur))
    return out


ABSENCE_TYPES = [
    # code, name, counts_as, kiosk, request, needs_approval, uses_vacation, payroll, color, icon, sort
    ("OBED", "Obed / prestávka", "break", 1, 0, 0, 0, "PREST", "#8a99ad", "🍽", 10),
    ("LEKAR", "Lekár", "paid", 1, 1, 1, 0, "LEK", "#d9534f", "⚕", 20),
    ("LEKAR_DOP", "Lekár – doprovod", "paid", 0, 1, 1, 0, "LEKD", "#e07b39", "⚕", 21),
    ("SLUZ", "Služobne / pochôdzka", "work", 1, 0, 0, 0, "SLUZ", "#2a7ab0", "💼", 30),
    ("SUKR", "Súkromne", "unpaid", 1, 0, 0, 0, "SUKR", "#6b7a90", "🚶", 40),
    ("DOV", "Dovolenka", "paid", 0, 1, 1, 1, "DOV", "#2e9e5b", "🌴", 50),
    ("PN", "PN – dočasná pracovná neschopnosť", "unpaid", 0, 1, 0, 0, "PN", "#b03a2e", "🤒", 60),
    ("OCR", "OČR – ošetrovanie člena rodiny", "unpaid", 0, 1, 0, 0, "OCR", "#c0663a", "👪", 61),
    ("SC", "Služobná cesta", "work", 0, 1, 1, 0, "SC", "#1f5fa0", "🚆", 70),
    ("HO", "Práca z domu (home office)", "work", 0, 1, 1, 0, "HO", "#5b6ee1", "🏠", 71),
    ("NV", "Náhradné voľno", "paid", 0, 1, 1, 0, "NV", "#7a5cc2", "⏳", 80),
    ("PV", "Platené voľno (§ 141 ZP)", "paid", 0, 1, 1, 0, "PV", "#3d9a9b", "📄", 81),
    ("NEP", "Neplatené voľno", "unpaid", 0, 1, 1, 0, "NEP", "#9a9a9a", "∅", 90),
]

SHIFT_TYPES = [
    ("D", "Denná 12 h (06–18)", "06:00", "18:00", 30, 1, "#f5b700"),
    ("N", "Nočná 12 h (18–06)", "18:00", "06:00", 30, 1, "#0b2d5b"),
    ("R", "Ranná 8 h (06–14)", "06:00", "14:30", 30, 0, "#4f9de0"),
    ("P", "Poobedná 8 h (14–22)", "14:00", "22:30", 30, 0, "#8e6bd1"),
    ("V", "Voľno", None, None, 0, 0, "#e6eaf0"),
]

EXPORT_PROFILES = [
    ("Mzdy – mesačný súhrn (CSV ; cp1250)", "csv", "month", ";", "cp1250", ",",
     ["personal_number", "last_name", "first_name", "month", "fond_h", "worked_days", "worked_h", "night_h",
      "weekend_h", "holiday_h", "holiday_paid_h", "over_fond_h", "vacation_days", "abs_d:DOV", "abs_h:LEKAR",
      "abs_k:PN", "abs_k:OCR", "abs_h:NV", "abs_d:NEP"]),
    ("Mzdy – riadky neprítomností (CSV UTF-8)", "csv", "absence", ";", "utf-8-sig", ",",
     ["personal_number", "month", "payroll_code", "name", "days", "cal_days", "hours"]),
    ("Kontrola – denné záznamy (Excel)", "xlsx", "day", ";", "utf-8", ",",
     ["personal_number", "full_name", "day", "shift", "planned_h", "first_in", "last_out", "worked_h", "night_h",
      "weekend_h", "holiday_h", "absences", "warnings"]),
    ("Mesačný súhrn (Excel)", "xlsx", "month", ";", "utf-8", ",",
     ["personal_number", "full_name", "org_unit", "cost_center", "fte", "fond_h", "worked_h", "night_h", "weekend_h",
      "holiday_h", "holiday_paid_h", "paid_absence_h", "balance_h", "vacation_days", "abs_d:DOV", "abs_k:PN",
      "abs_h:LEKAR"]),
    ("Integrácia – XML", "xml", "month", ";", "utf-8", ".",
     ["personal_number", "month", "fond_h", "worked_h", "night_h", "weekend_h", "holiday_h", "vacation_days"]),
    ("Integrácia – JSON (denné)", "json", "day", ";", "utf-8", ".",
     ["personal_number", "day", "shift", "planned_h", "worked_h", "night_h", "absences"]),
]


def header_for(field):
    from .exports import MONTH_FIELDS, DAY_FIELDS, ABSENCE_FIELDS
    if field.startswith("abs_h:"):
        return f"{field[6:]} (h)"
    if field.startswith("abs_d:"):
        return f"{field[6:]} (prac. dni)"
    if field.startswith("abs_k:"):
        return f"{field[6:]} (kal. dni)"
    return MONTH_FIELDS.get(field) or DAY_FIELDS.get(field) or ABSENCE_FIELDS.get(field) or field


def base(con, admin_password=None):
    for code, name, ca, k, rq, na, uv, pc, col, ic, so in ABSENCE_TYPES:
        con.execute("INSERT OR IGNORE INTO absence_types VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (code, name, ca, k, rq, na, uv, pc, col, ic, so))
    for st in SHIFT_TYPES:
        con.execute("INSERT OR IGNORE INTO shift_types(code,name,start,end,break_min,break_paid,color) VALUES (?,?,?,?,?,?,?)", st)
    for y in (2026, 2027, 2028):
        for d, n, off, sur in holidays_for(y):
            con.execute("INSERT OR IGNORE INTO holidays VALUES (?,?,?,?)", (d, n, off, sur))
    if not con.execute("SELECT 1 FROM export_profiles").fetchone():
        for name, fmt, level, de, enc, dec, fields in EXPORT_PROFILES:
            cols = [{"field": f, "header": header_for(f)} for f in fields]
            con.execute("INSERT INTO export_profiles(name,fmt,level,delimiter,encoding,decimal,columns) VALUES (?,?,?,?,?,?,?)",
                        (name, fmt, level, de, enc, dec, json.dumps(cols, ensure_ascii=False)))
    db.set_setting(con, "company", "Bratislavská integrovaná doprava, a.s.")
    if db.get_setting(con, "auto_break") is None:
        db.set_setting(con, "auto_break", True)
        db.set_setting(con, "min_rest_h", 12)
        db.set_setting(con, "kiosk_debounce_s", 60)
        db.set_setting(con, "require_totp_roles", ["admin"])
        db.set_setting(con, "session_hours", 10)
    if not con.execute("SELECT 1 FROM schedules").fetchone():
        con.execute("INSERT INTO schedules(name,kind,weekly_hours,params) VALUES (?,?,?,?)",
                    ("Pevný 7:30–15:30 (37,5 h)", "fixed", 37.5, json.dumps({"start": "07:30", "end": "15:30", "break_min": 30, "workdays": [0, 1, 2, 3, 4]})))
        con.execute("INSERT INTO schedules(name,kind,weekly_hours,params) VALUES (?,?,?,?)",
                    ("Pružný – jadro 9:00–14:00 (37,5 h)", "flex", 37.5, json.dumps({"window_from": "06:00", "window_to": "19:00", "core_from": "09:00", "core_to": "14:00", "break_min": 30, "workdays": [0, 1, 2, 3, 4]})))
        con.execute("INSERT INTO schedules(name,kind,weekly_hours,params) VALUES (?,?,?,?)",
                    ("Dispečing 24/7 – nepretržitá prevádzka (37,5 h)", "shift", 37.5, json.dumps({"pattern": ["D", "N", "V", "V"], "anchor": "2026-01-01", "min_rest_h": 8})))
    if not con.execute("SELECT 1 FROM users").fetchone():
        pw = admin_password or secrets.token_urlsafe(10)
        con.execute("INSERT INTO users(username,password_hash,roles,must_change_pw) VALUES (?,?,?,?)",
                    ("admin", db.hash_password(pw), "admin,personalista", 1 if not admin_password else 0))
        return pw
    return None


DEMO_UNITS = [
    # key, name, short, kind, parent, cost_center
    ("ROOT", "Bratislavská integrovaná doprava, a.s.", "BID", "spolocnost", None, "1000"),
    ("GR", "Generálny riaditeľ", "GR", "riaditel", "ROOT", "1000"),
    ("UE", "Ekonomický úsek", "EÚ", "usek", "GR", "2000"),
    ("OFU", "Odbor financií a účtovníctva", "OFÚ", "odbor", "UE", "2100"),
    ("OPM", "Oddelenie personalistiky a miezd", "OPM", "oddelenie", "UE", "2200"),
    ("UD", "Úsek dopravy", "ÚD", "usek", "GR", "3000"),
    ("OPD", "Odbor plánovania dopravy", "OPD", "odbor", "UD", "3100"),
    ("DISP", "Dispečing IDS BK (24/7)", "DISP", "dispecing", "UD", "3200"),
    ("UIT", "Úsek IT a tarifných systémov", "IT", "usek", "GR", "4000"),
]
DEMO_EMP = [
    # pn, first, last, unit, position, schedule_idx, fte, roles, manager_of
    ("1001", "Martin", "Kováč", "GR", "generálny riaditeľ", 0, 1.0, "veduci,zamestnanec", "GR"),
    ("1002", "Zuzana", "Horváthová", "UE", "riaditeľka ekonomického úseku", 1, 1.0, "veduci,zamestnanec", "UE"),
    ("1003", "Peter", "Novák", "OFU", "vedúci odboru", 1, 1.0, "veduci,zamestnanec", "OFU"),
    ("1004", "Jana", "Šimková", "OFU", "účtovníčka", 1, 1.0, "zamestnanec", None),
    ("1005", "Lucia", "Baláž", "OPM", "personalistka – mzdová účtovníčka", 0, 1.0, "personalista,veduci,zamestnanec", "OPM"),
    ("1006", "Eva", "Krajčírová", "OPM", "mzdová účtovníčka", 0, 0.5, "personalista,zamestnanec", None),
    ("1007", "Tomáš", "Varga", "UD", "riaditeľ úseku dopravy", 1, 1.0, "veduci,zamestnanec", "UD"),
    ("1008", "Michal", "Polák", "OPD", "vedúci odboru plánovania", 1, 1.0, "veduci,zamestnanec", "OPD"),
    ("1009", "Katarína", "Lukáčová", "OPD", "plánovačka dopravy", 1, 1.0, "zamestnanec", None),
    ("1010", "Róbert", "Molnár", "DISP", "vedúci dispečingu", 1, 1.0, "veduci,zamestnanec", "DISP"),
    ("1011", "Andrej", "Hudák", "DISP", "dispečer", 2, 1.0, "zamestnanec", None),
    ("1012", "Simona", "Tóthová", "DISP", "dispečerka", 2, 1.0, "zamestnanec", None),
    ("1013", "Juraj", "Kollár", "DISP", "dispečer", 2, 1.0, "zamestnanec", None),
    ("1014", "Veronika", "Mészárosová", "DISP", "dispečerka", 2, 1.0, "zamestnanec", None),
    ("1015", "Filip", "Gajdoš", "UIT", "riaditeľ úseku IT", 1, 1.0, "veduci,admin,zamestnanec", "UIT"),
    ("1016", "Patrik", "Urban", "UIT", "správca IT", 1, 1.0, "zamestnanec", None),
]


def demo(con, today: date | None = None):
    rnd = random.Random(42)
    today = today or date.today()
    unit_ids = {}
    for key, name, short, kind, parent, cc in DEMO_UNITS:
        cur = con.execute("INSERT INTO org_units(name,short,kind,parent_id,cost_center) VALUES (?,?,?,?,?)",
                          (name, short, kind, unit_ids.get(parent), cc))
        unit_ids[key] = cur.lastrowid
    sched_ids = [r["id"] for r in db.rows(con, "SELECT id FROM schedules ORDER BY id")]
    emp_ids = {}
    for i, (pn, fn, ln, unit, pos, si, fte, roles, mgr) in enumerate(DEMO_EMP):
        uid = f"04A1{int(pn):04d}B2C3D4"
        cur = con.execute(
            "INSERT INTO employees(personal_number,first_name,last_name,email,position,org_unit_id,schedule_id,fte,chip_uid,allow_remote,start_date,vacation_days,vacation_carry) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pn, fn, ln, f"{fn.lower()}.{ln.lower()}@bid.sk".translate(str.maketrans("áäčďéíĺľňóôŕšťúýž", "aacdeillnoorstuyz")), pos, unit_ids[unit],
             sched_ids[si], fte, uid, 1 if si != 2 else 0, "2020-01-01", 30 if int(pn) < 1004 else 25, rnd.choice([0, 2, 4.5])))
        emp_ids[pn] = cur.lastrowid
        if mgr:
            con.execute("UPDATE org_units SET manager_id=? WHERE id=?", (cur.lastrowid, unit_ids[mgr]))
        uname = (fn[0] + ln).lower().translate(str.maketrans("áäčďéíĺľňóôŕšťúýž", "aacdeillnoorstuyz"))
        con.execute("INSERT INTO users(employee_id,username,password_hash,roles,must_change_pw) VALUES (?,?,?,?,0)",
                    (cur.lastrowid, uname, db.hash_password("Demo2026!"), roles))
    con.execute("UPDATE org_units SET manager_id=? WHERE id=?", (emp_ids["1001"], unit_ids["ROOT"]))
    con.execute("UPDATE org_units SET deputy_id=? WHERE id=?", (emp_ids["1011"], unit_ids["DISP"]))

    # rozpis zmien dispečing: D N V V s posunom
    pattern = ["D", "N", "V", "V"]
    start = date(today.year, today.month, 1) - timedelta(days=40)
    end = date(today.year, today.month, 1) + timedelta(days=45)
    disp = ["1011", "1012", "1013", "1014"]
    for off, pn in enumerate(disp):
        d = start
        while d <= end:
            code = pattern[((d - date(2026, 1, 1)).days + off) % 4]
            con.execute("INSERT OR REPLACE INTO roster VALUES (?,?,?)", (emp_ids[pn], d.isoformat(), code))
            d += timedelta(days=1)

    # kiosk zariadenia
    con.execute("INSERT INTO devices(name,location,key_hash) VALUES (?,?,?)",
                ("Terminál Recepcia", "Vstup – Mlynské nivy", db.sha256("demo-kiosk-key")))
    con.execute("INSERT INTO devices(name,location,key_hash) VALUES (?,?,?)",
                ("Terminál Dispečing", "Dispečerská sála", db.sha256("demo-kiosk-key-2")))

    # žiadosti
    def req(pn, code, f, t, status, note=""):
        con.execute("INSERT INTO requests(employee_id,type_code,date_from,date_to,note,status,created_at,decided_at) VALUES (?,?,?,?,?,?,?,?)",
                    (emp_ids[pn], code, f.isoformat(), t.isoformat(), note, status, datetime.now().isoformat(timespec="seconds"),
                     datetime.now().isoformat(timespec="seconds") if status != "pending" else None))

    m1 = date(today.year, today.month, 1)
    req("1004", "DOV", m1 + timedelta(days=9), m1 + timedelta(days=11), "approved", "rodinná dovolenka")
    req("1009", "DOV", today + timedelta(days=12), today + timedelta(days=16), "pending", "Vianoce")
    req("1016", "PN", m1 + timedelta(days=2), m1 + timedelta(days=5), "approved")
    req("1006", "LEKAR", today + timedelta(days=3), today + timedelta(days=3), "pending", "kontrola")
    req("1012", "DOV", today + timedelta(days=20), today + timedelta(days=22), "pending")

    # udalosti za predchádzajúci a aktuálny mesiac (do včera + dnešný príchod)
    def ev(pn, dt, kind, reason=None, src="kiosk"):
        con.execute("INSERT INTO events(employee_id,ts,kind,reason,source,device_id,created_at) VALUES (?,?,?,?,?,?,?)",
                    (emp_ids[pn], dt.isoformat(timespec="seconds"), kind, reason, src, 1, dt.isoformat(timespec="seconds")))

    absent = {(emp_ids["1004"], (m1 + timedelta(days=k)).isoformat()) for k in (9, 10, 11)}
    absent |= {(emp_ids["1016"], (m1 + timedelta(days=k)).isoformat()) for k in (2, 3, 4, 5)}
    hol = {r["day"] for r in db.rows(con, "SELECT day FROM holidays WHERE day_off=1")}
    d = m1 - timedelta(days=31)
    while d <= today:
        for pn, fn, ln, unit, pos, si, fte, roles, mgr in DEMO_EMP:
            eid = emp_ids[pn]
            if (eid, d.isoformat()) in absent:
                continue
            if si == 2:
                code = pattern[((d - date(2026, 1, 1)).days + disp.index(pn)) % 4]
                if code == "V":
                    continue
                if code == "D":
                    s = datetime.combine(d, datetime.min.time()) + timedelta(hours=5, minutes=50 + rnd.randint(0, 8))
                    e = datetime.combine(d, datetime.min.time()) + timedelta(hours=18, minutes=rnd.randint(1, 12))
                else:
                    s = datetime.combine(d, datetime.min.time()) + timedelta(hours=17, minutes=50 + rnd.randint(0, 8))
                    e = datetime.combine(d + timedelta(days=1), datetime.min.time()) + timedelta(hours=6, minutes=rnd.randint(1, 12))
                ev(pn, s, "IN", src="kiosk")
                if e <= datetime.now():
                    ev(pn, e, "OUT", src="kiosk")
                continue
            if d.weekday() >= 5 or d.isoformat() in hol:
                continue
            start_h = 7 if si == 0 else rnd.choice([6, 7, 8])
            s = datetime.combine(d, datetime.min.time()) + timedelta(hours=start_h, minutes=rnd.randint(10, 35))
            hours_day = 7.5 * fte + (0.5 if fte == 1 else 0) + rnd.choice([0, 0, 0.25, 0.5, -0.25])
            nowdt = datetime.now()
            if s > nowdt:
                continue
            ev(pn, s, "IN")
            lunch = s + timedelta(hours=4 if fte == 1 else 2, minutes=rnd.randint(0, 40))
            if fte == 1 and lunch + timedelta(minutes=30) < nowdt:
                ev(pn, lunch, "OUT", "OBED")
                ev(pn, lunch + timedelta(minutes=30), "IN")
            if rnd.random() < 0.06 and s + timedelta(hours=4) < nowdt:
                lk = s + timedelta(hours=2)
                ev(pn, lk, "OUT", "LEKAR")
                ev(pn, lk + timedelta(minutes=90), "IN")
            e = s + timedelta(hours=hours_day)
            if e > nowdt:
                continue
            if not (pn == "1009" and d == today - timedelta(days=1 if today.weekday() != 0 else 3)):
                ev(pn, e, "OUT")  # 1009 má "zabudnutý odchod" – ukážka upozornenia
        d += timedelta(days=1)
    return emp_ids


if __name__ == "__main__":
    db.init_db()
    with db.tx() as con:
        pw = base(con, admin_password="Admin2026!" if "--demo" in sys.argv else None)
        if "--demo" in sys.argv and not con.execute("SELECT 1 FROM employees").fetchone():
            demo(con)
            print("Demo dáta vytvorené. Prihlásenie: admin / Admin2026!  |  zamestnanci: napr. jsimkova / Demo2026!")
        elif pw:
            print(f"Vytvorený používateľ admin s heslom: {pw}  (pri prvom prihlásení ho zmeňte)")
