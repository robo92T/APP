"""Testy výpočtu dochádzky (spustenie: python -m pytest -q)."""
from datetime import datetime

from backend import calc
from backend.seed import ABSENCE_TYPES, SHIFT_TYPES, holidays_for

TYPES = {a[0]: {"code": a[0], "name": a[1], "counts_as": a[2], "uses_vacation": a[6]} for a in ABSENCE_TYPES}
SHIFTS = {s[0]: {"code": s[0], "start": s[2], "end": s[3], "break_min": s[4], "break_paid": s[5]} for s in SHIFT_TYPES}
HOL = {d: {"day": d, "name": n, "day_off": o, "surcharge": s} for d, n, o, s in holidays_for(2026)}
FIXED = {"id": 1, "kind": "fixed", "weekly_hours": 37.5, "params": {"start": "07:30", "end": "15:30", "break_min": 30, "workdays": [0, 1, 2, 3, 4]}}
SHIFT = {"id": 3, "kind": "shift", "weekly_hours": 37.5, "params": {"min_rest_h": 8}}
EMP = {"id": 1, "fte": 1.0}
NOW = datetime(2026, 12, 15, 12, 0)


def ev(ts, kind, reason=None):
    return {"ts": ts, "kind": kind, "reason": reason, "deleted": 0}


def day(res, d):
    return next(x for x in res["days"] if x["day"] == d)


def run(events, sched=FIXED, requests=(), roster=None, emp=EMP, month="2026-11"):
    return calc.compute_month(month, emp, sched, events, list(requests), roster or {}, SHIFTS, HOL, TYPES, {"auto_break": True}, now=NOW)


def test_normal_day_with_lunch():
    r = run([ev("2026-11-02T07:30:00", "IN"), ev("2026-11-02T11:30:00", "OUT", "OBED"),
             ev("2026-11-02T12:00:00", "IN"), ev("2026-11-02T16:00:00", "OUT")])
    d = day(r, "2026-11-02")
    assert d["planned_h"] == 7.5
    assert d["worked_h"] == 8.0           # 4 + 4, obed sa nezapočíta
    assert d["break_h"] == 0.5
    assert d["auto_break_h"] == 0
    assert d["first_in"] == "07:30" and d["last_out"] == "16:00"


def test_auto_break_when_no_lunch_recorded():
    r = run([ev("2026-11-03T07:00:00", "IN"), ev("2026-11-03T15:00:00", "OUT")])
    d = day(r, "2026-11-03")
    assert d["auto_break_h"] == 0.5 and d["worked_h"] == 7.5


def test_doctor_is_paid_absence_and_private_is_not():
    r = run([ev("2026-11-04T07:30:00", "IN"), ev("2026-11-04T09:00:00", "OUT", "LEKAR"),
             ev("2026-11-04T11:00:00", "IN"), ev("2026-11-04T12:00:00", "OUT", "SUKR"),
             ev("2026-11-04T12:30:00", "IN"), ev("2026-11-04T16:00:00", "OUT")])
    d = day(r, "2026-11-04")
    assert d["absences"]["LEKAR"] == 2.0
    assert d["absences"]["SUKR"] == 0.5
    assert d["worked_h"] == 1.5 + 1 + 3.5
    assert d["covered_h"] == 2.0          # lekár pokrýva fond, súkromne nie


def test_night_shift_across_midnight_and_month_end():
    roster = {"2026-11-30": "N"}
    events = [ev("2026-11-30T18:00:00", "IN"), ev("2026-12-01T06:00:00", "OUT")]
    r = run(events, sched=SHIFT, roster=roster)
    d = day(r, "2026-11-30")
    assert d["worked_h"] == 6.0           # do polnoci
    assert d["night_h"] == 2.0            # 22–24
    assert d["planned_h"] == 6.0          # plán sa delí o polnoci (prestávka platená – § 91 ods. 5 ZP)
    assert d["shift"] == "N"
    r12 = run(events, sched=SHIFT, roster=roster, month="2026-12")
    assert day(r12, "2026-12-01")["planned_h"] == 6.0
    assert day(r12, "2026-12-01")["worked_h"] == 6.0
    assert day(r12, "2026-12-01")["night_h"] == 6.0


def test_paid_break_shift_no_auto_break():
    roster = {"2026-11-05": "D"}
    r = run([ev("2026-11-05T06:00:00", "IN"), ev("2026-11-05T18:00:00", "OUT")], sched=SHIFT, roster=roster)
    assert day(r, "2026-11-05")["worked_h"] == 12.0


def test_short_rest_warning():
    roster = {"2026-11-05": "D", "2026-11-06": "N"}
    r = run([ev("2026-11-05T06:00:00", "IN"), ev("2026-11-05T18:00:00", "OUT"),
             ev("2026-11-06T00:30:00", "IN"), ev("2026-11-06T06:00:00", "OUT")], sched=SHIFT, roster=roster)
    assert any("Odpočinok" in w for w in day(r, "2026-11-06")["warnings"])


def test_vacation_request_counts_days_and_covers_fond():
    req = {"status": "approved", "type_code": "DOV", "date_from": "2026-11-09", "date_to": "2026-11-15", "half_day": 0}
    r = run([], requests=[req])
    assert r["summary"]["vacation_days"] == 5          # víkend sa nepočíta
    assert r["summary"]["absence_days"]["DOV"] == 5
    assert day(r, "2026-11-09")["covered_h"] == 7.5
    assert r["summary"]["absence_cal_days"]["DOV"] == 7


def test_holidays_2026_rules():
    # 1. 9. 2026 – nie je deň pracovného pokoja; 8. 5. 2026 – § 4b, tiež pracovný deň
    r9 = run([], month="2026-09")
    assert day(r9, "2026-09-01")["planned_h"] == 7.5
    assert day(r9, "2026-09-15")["planned_h"] == 7.5
    r5 = run([], month="2026-05")
    assert day(r5, "2026-05-01")["planned_h"] == 0 and day(r5, "2026-05-01")["holiday_paid_h"] == 7.5
    assert day(r5, "2026-05-08")["planned_h"] == 7.5
    r4 = run([], month="2026-04")
    assert day(r4, "2026-04-03")["holiday"] == "Veľký piatok"
    assert day(r4, "2026-04-06")["holiday"] == "Veľkonočný pondelok"


def test_part_time_fond():
    r = run([], emp={"id": 2, "fte": 0.5})
    assert r["summary"]["fond_h"] == 21 * 3.75


def test_missing_out_detected():
    r = run([ev("2026-11-10T07:30:00", "IN"), ev("2026-11-11T07:30:00", "IN"), ev("2026-11-11T15:30:00", "OUT")])
    assert any("Chýba odchod" in w for w in day(r, "2026-11-10")["warnings"])
    assert day(r, "2026-11-11")["worked_h"] == 7.5      # 8 h – automatická prestávka


def test_holidays_2027_back_to_normal():
    h = {d: o for d, n, o, s in holidays_for(2027)}
    assert h["2027-05-08"] == 1 and h["2027-09-15"] == 1 and h["2027-09-01"] == 0
