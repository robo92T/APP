"""Výpočet dochádzky – srdce systému.

Princíp (jednoduchý a overiteľný):
1. Záznamy IN (príchod) a OUT (odchod s dôvodom) sa poskladajú do intervalov.
   - IN -> OUT  = prítomnosť v práci
   - OUT s dôvodom (napr. LEKAR) -> nasledujúci IN = interval daného dôvodu
2. Intervaly sa rozdelia o polnoci na kalendárne dni (nočné zmeny).
3. Každý deň dostane plánovaný fond (podľa režimu / rozpisu zmien), odpracované
   hodiny, nočnú prácu (22–6, § 98 ods. 1 ZP), víkend, sviatok, neprítomnosti
   (zo schválených žiadostí) a upozornenia (chýbajúci odchod, krátky odpočinok...).
4. Mesačný súhrn = súčet dní. Klasifikáciu nadčasu (§ 97 ZP) robí človek/mzdy –
   systém ukazuje hodiny nad fond.
"""
from __future__ import annotations

import calendar
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

NIGHT_FROM = time(22, 0)
NIGHT_TO = time(6, 0)


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def hm(s: str | None) -> time | None:
    if not s:
        return None
    h, m = s.split(":")[:2]
    return time(int(h), int(m))


def hours(td: timedelta) -> float:
    return td.total_seconds() / 3600.0


def month_days(month: str):
    y, m = map(int, month.split("-"))
    n = calendar.monthrange(y, m)[1]
    return [date(y, m, d) for d in range(1, n + 1)]


def overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> timedelta:
    s, e = max(a0, b0), min(a1, b1)
    return e - s if e > s else timedelta(0)


def night_hours(s: datetime, e: datetime) -> float:
    """Hodiny v čase 22:00–06:00 v rámci intervalu (interval je v rámci jedného dňa)."""
    d = s.date()
    total = overlap(s, e, datetime.combine(d, time(0)), datetime.combine(d, NIGHT_TO))
    total += overlap(s, e, datetime.combine(d, NIGHT_FROM), datetime.combine(d + timedelta(days=1), time(0)))
    return hours(total)


def split_by_day(s: datetime, e: datetime):
    out = []
    cur = s
    while cur < e:
        nxt = datetime.combine(cur.date() + timedelta(days=1), time(0))
        end = min(e, nxt)
        out.append((cur, end))
        cur = end
    return out


@dataclass
class Interval:
    start: datetime
    end: datetime
    kind: str            # WORK / absence code
    counts_as: str       # work / paid / unpaid / break
    open: bool = False   # chýba ukončenie


@dataclass
class Day:
    day: date
    planned_h: float = 0.0
    shift: str | None = None
    plan_from: str | None = None
    plan_to: str | None = None
    is_weekend: bool = False
    holiday: str | None = None
    holiday_day_off: bool = False
    holiday_surcharge: bool = False
    worked_h: float = 0.0
    night_h: float = 0.0
    weekend_h: float = 0.0
    holiday_h: float = 0.0
    holiday_paid_h: float = 0.0
    break_h: float = 0.0
    auto_break_h: float = 0.0
    absences: dict = field(default_factory=lambda: defaultdict(float))
    absence_full: list = field(default_factory=list)
    absence_cal: list = field(default_factory=list)  # kalendárne dni neprítomnosti (PN, OČR)
    covered_h: float = 0.0       # hodiny neprítomnosti, ktoré "pokrývajú" fond (dovolenka, PN, lekár...)
    vacation_days: float = 0.0
    first_in: str | None = None
    last_out: str | None = None
    intervals: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self):
        return {
            "day": self.day.isoformat(),
            "weekday": self.day.weekday(),
            "planned_h": round(self.planned_h, 2),
            "shift": self.shift,
            "plan_from": self.plan_from,
            "plan_to": self.plan_to,
            "is_weekend": self.is_weekend,
            "holiday": self.holiday,
            "holiday_day_off": self.holiday_day_off,
            "worked_h": round(self.worked_h, 2),
            "night_h": round(self.night_h, 2),
            "weekend_h": round(self.weekend_h, 2),
            "holiday_h": round(self.holiday_h, 2),
            "holiday_paid_h": round(self.holiday_paid_h, 2),
            "break_h": round(self.break_h, 2),
            "auto_break_h": round(self.auto_break_h, 2),
            "absences": {k: round(v, 2) for k, v in self.absences.items() if v},
            "absence_full": self.absence_full,
            "covered_h": round(self.covered_h, 2),
            "vacation_days": self.vacation_days,
            "first_in": self.first_in,
            "last_out": self.last_out,
            "intervals": self.intervals,
            "warnings": self.warnings,
        }


def shift_window(day: date, st: dict):
    """Vráti (začiatok, koniec, hodiny_netto) plánovanej zmeny."""
    a, b = hm(st.get("start")), hm(st.get("end"))
    if not a or not b:
        return None, None, 0.0
    s = datetime.combine(day, a)
    e = datetime.combine(day, b)
    if e <= s:
        e += timedelta(days=1)
    net = hours(e - s)
    if not st.get("break_paid"):
        net -= (st.get("break_min") or 0) / 60.0
    return s, e, max(net, 0.0)


def build_intervals(events: list[dict], types: dict, now: datetime) -> tuple[list[Interval], list[tuple[datetime, str]]]:
    """Z udalostí IN/OUT poskladá intervaly. Vráti aj upozornenia (čas, text)."""
    evs = sorted((e for e in events if not e.get("deleted")), key=lambda e: e["ts"])
    out: list[Interval] = []
    warns = []
    presence_start = None
    absence = None  # (start, code)
    for e in evs:
        t = parse_dt(e["ts"])
        if e["kind"] == "IN":
            if absence:
                code = absence[1]
                out.append(Interval(absence[0], t, code, types.get(code, {}).get("counts_as", "unpaid")))
                absence = None
            if presence_start is not None:
                if t - presence_start > timedelta(hours=16):
                    # predchádzajúci deň bez odchodu – ten interval sa nezapočíta, začína nový
                    warns.append((presence_start, "Chýba odchod – deň treba opraviť"))
                else:
                    warns.append((t, "Dvojitý príchod bez odchodu – prvý príchod ponechaný"))
                    continue
            presence_start = t
        else:  # OUT
            if presence_start is None:
                if absence is None:
                    warns.append((t, "Odchod bez predchádzajúceho príchodu"))
                continue
            out.append(Interval(presence_start, t, "WORK", "work"))
            presence_start = None
            if e.get("reason"):
                absence = (t, e["reason"])
    if presence_start is not None:
        # otvorená prítomnosť – ak je to dnes, počítame do "teraz"
        if presence_start.date() >= (now - timedelta(hours=16)).date() and now > presence_start and (now - presence_start) < timedelta(hours=16):
            out.append(Interval(presence_start, now, "WORK", "work", open=True))
        else:
            warns.append((presence_start, "Chýba odchod – deň treba opraviť"))
    if absence is not None:
        warns.append((absence[0], f"Odchod s dôvodom {absence[1]} bez návratu"))
        absence_end = None
        absence_start, code = absence
        # neukončený dôvod: ak dnes – do teraz, inak sa nezapočíta
        if absence_start.date() == now.date() and now > absence_start:
            absence_end = now
        if absence_end:
            out.append(Interval(absence_start, absence_end, code, types.get(code, {}).get("counts_as", "unpaid"), open=True))
    return out, warns


def plan_for_day(d: date, emp: dict, sched: dict | None, roster: dict, shift_types: dict, holidays: dict):
    """Plánovaný fond pre deň. Pre pevný/pružný režim: týždenný fond * úväzok / 5 v pracovné dni."""
    hol = holidays.get(d.isoformat())
    if not sched:
        return 0.0, None, None, None
    kind = sched["kind"]
    params = sched.get("params") or {}
    if isinstance(params, str):
        params = json.loads(params or "{}")
    if kind == "shift":
        code = roster.get(d.isoformat())
        if not code:
            return 0.0, None, None, None
        st = shift_types.get(code) or {}
        s, e, net = shift_window(d, st)
        return net, code, (s.strftime("%H:%M") if s else None), (e.strftime("%H:%M") if e else None)
    # fixed / flex
    workdays = params.get("workdays", [0, 1, 2, 3, 4])
    if d.weekday() not in workdays:
        return 0.0, None, None, None
    if hol and hol["day_off"]:
        return 0.0, None, None, None
    daily = sched["weekly_hours"] * float(emp.get("fte") or 1.0) / max(len(workdays), 1)
    pf = params.get("start") if kind == "fixed" else params.get("core_from")
    pt = params.get("end") if kind == "fixed" else params.get("core_to")
    return daily, None, pf, pt


def compute_month(month: str, emp: dict, sched: dict | None, events: list[dict], requests: list[dict],
                  roster: dict, shift_types: dict, holidays: dict, types: dict, settings: dict | None = None,
                  now: datetime | None = None, prev_events: list[dict] | None = None) -> dict:
    settings = settings or {}
    now = now or datetime.now()
    days = month_days(month)
    first, last = days[0], days[-1]
    dmap: dict[date, Day] = {}
    sched_params = {}
    if sched:
        sched_params = sched.get("params") or {}
        if isinstance(sched_params, str):
            sched_params = json.loads(sched_params or "{}")

    for d in days:
        dd = Day(day=d, is_weekend=d.weekday() >= 5)
        hol = holidays.get(d.isoformat())
        if hol:
            dd.holiday = hol["name"]
            dd.holiday_day_off = bool(hol["day_off"])
            dd.holiday_surcharge = bool(hol["surcharge"])
        dd.planned_h, dd.shift, dd.plan_from, dd.plan_to = plan_for_day(d, emp, sched, roster, shift_types, holidays)
        # Sviatok v pracovný deň u pevného/pružného režimu -> náhrada mzdy za sviatok (§ 122 ZP)
        if sched and sched["kind"] != "shift" and hol and hol["day_off"] and d.weekday() in sched_params.get("workdays", [0, 1, 2, 3, 4]):
            dd.holiday_paid_h = sched["weekly_hours"] * float(emp.get("fte") or 1.0) / max(len(sched_params.get("workdays", [0, 1, 2, 3, 4])), 1)
        dmap[d] = dd

    # zmenový režim: plán nočnej zmeny sa delí na kalendárne dni rovnako ako odpracovaný čas
    if sched and sched["kind"] == "shift":
        for dd in dmap.values():
            dd.planned_h = 0.0
        for day_iso, code in roster.items():
            st = shift_types.get(code) or {}
            s0, e0, net = shift_window(date.fromisoformat(day_iso), st)
            if not s0 or net <= 0:
                continue
            total = hours(e0 - s0)
            for a, b in split_by_day(s0, e0):
                if a.date() in dmap:
                    dmap[a.date()].planned_h += net * hours(b - a) / total

    all_events = list(prev_events or []) + list(events)
    intervals, warns = build_intervals(all_events, types, now)
    for t, w in warns:
        if t.date() in dmap:
            dmap[t.date()].warnings.append(w)

    # rozdelenie intervalov na dni
    work_segments_by_day = defaultdict(list)
    for iv in intervals:
        for s, e in split_by_day(iv.start, iv.end):
            d = s.date()
            if d not in dmap:
                continue
            dd = dmap[d]
            h = hours(e - s)
            dd.intervals.append({"from": s.strftime("%H:%M"), "to": e.strftime("%H:%M") if e.time() != time(0) else "24:00",
                                 "kind": iv.kind, "open": iv.open})
            if iv.counts_as == "work":
                dd.worked_h += h
                dd.night_h += night_hours(s, e)
                if dd.is_weekend:
                    dd.weekend_h += h
                if dd.holiday and dd.holiday_surcharge:
                    dd.holiday_h += h
                if iv.kind == "WORK":
                    work_segments_by_day[d].append((s, e))
                else:
                    dd.absences[iv.kind] += h
            elif iv.counts_as == "break":
                dd.break_h += h
            else:
                dd.absences[iv.kind] += h
                if iv.counts_as == "paid":
                    dd.covered_h += h
            if iv.kind == "WORK":
                if dd.first_in is None or s.strftime("%H:%M") < dd.first_in:
                    dd.first_in = s.strftime("%H:%M")
                lo = e.strftime("%H:%M") if e.time() != time(0) else "24:00"
                if dd.last_out is None or lo > dd.last_out:
                    dd.last_out = lo

    # automatická prestávka (§ 91 ZP): zmena > 6 h a žiadna zaznamenaná prestávka
    auto_break = settings.get("auto_break", True)
    for iv in intervals:
        if iv.kind != "WORK":
            continue
        length = hours(iv.end - iv.start)
        d = iv.start.date()
        if d not in dmap or length <= 6.0 or not auto_break:
            continue
        dd = dmap[d]
        break_paid = False
        brk_min = sched_params.get("break_min", 30)
        if dd.shift and dd.shift in shift_types:
            break_paid = bool(shift_types[dd.shift].get("break_paid"))
            brk_min = shift_types[dd.shift].get("break_min", 30)
        if break_paid or dd.break_h >= brk_min / 60.0 - 1e-6:
            continue
        missing = brk_min / 60.0 - dd.break_h
        dd.auto_break_h += missing
        dd.worked_h -= missing
        # odpočítame z prvej časti dňa (zjednodušenie – nočné hodiny neupravujeme)

    # schválené žiadosti
    for r in requests:
        if r["status"] != "approved":
            continue
        t = types.get(r["type_code"], {})
        rf, rt = date.fromisoformat(r["date_from"]), date.fromisoformat(r["date_to"])
        cur = max(rf, first)
        while cur <= min(rt, last):
            dd = dmap[cur]
            if r.get("time_from") and r.get("time_to"):
                s = datetime.combine(cur, hm(r["time_from"]))
                e = datetime.combine(cur, hm(r["time_to"]))
                h = max(hours(e - s), 0)
                if t.get("counts_as") == "work":
                    dd.worked_h += h
                else:
                    dd.covered_h += h
                dd.absences[r["type_code"]] += h
            else:
                factor = 0.5 if r.get("half_day") else 1.0
                h = dd.planned_h * factor
                if t.get("counts_as") == "work" and h:
                    dd.worked_h += h
                elif h:
                    dd.covered_h += h
                dd.absences[r["type_code"]] += h
                if dd.planned_h > 0:
                    dd.absence_full.append(r["type_code"] if factor == 1 else r["type_code"] + "/2")
                dd.absence_cal.append(r["type_code"])
                if t.get("uses_vacation") and dd.planned_h > 0:
                    dd.vacation_days += factor
                if dd.worked_h > 0 and dd.planned_h > 0 and t.get("counts_as") != "work":
                    dd.warnings.append(f"Záznam práce v deň neprítomnosti ({t.get('name', r['type_code'])})")
            cur += timedelta(days=1)

    # kontroly ZP
    min_rest = float(sched_params.get("min_rest_h", settings.get("min_rest_h", 12)))
    work_ivs = sorted([iv for iv in intervals if iv.kind == "WORK"], key=lambda i: i.start)
    # zlúčime intervaly s krátkou pauzou (< 2 h) do "smeny"
    shifts = []
    for iv in work_ivs:
        if shifts and iv.start - shifts[-1][1] < timedelta(hours=2):
            shifts[-1][1] = max(shifts[-1][1], iv.end)
        else:
            shifts.append([iv.start, iv.end])
    for i in range(1, len(shifts)):
        rest = hours(shifts[i][0] - shifts[i - 1][1])
        d = shifts[i][0].date()
        if d in dmap and rest < min_rest:
            dmap[d].warnings.append(f"Odpočinok medzi zmenami {rest:.1f} h < {min_rest:g} h (§ 92 ZP)")
    open_ends = {iv.end for iv in work_ivs if iv.open}
    for s, e in shifts:
        if e in open_ends:
            continue
        if hours(e - s) > 12.5 and s.date() in dmap:
            dmap[s.date()].warnings.append(f"Zmena {hours(e - s):.1f} h – prekročená 12 h dĺžka")
    for d, dd in dmap.items():
        if dd.planned_h > 0 and dd.worked_h == 0 and not dd.absence_full and not dd.absence_cal and d < now.date() and not any(dd.absences.values()):
            dd.warnings.append("Plánovaný pracovný deň bez záznamu a bez žiadosti")

    # týždenná kontrola 48 h (informatívne; § 85 ods. 9 ZP hovorí o priemere)
    week = defaultdict(float)
    for d, dd in dmap.items():
        week[d.isocalendar()[1]] += dd.worked_h
    for d, dd in dmap.items():
        if d.weekday() == 6 and week[d.isocalendar()[1]] > 48:
            dd.warnings.append(f"Týždeň {d.isocalendar()[1]}: {week[d.isocalendar()[1]]:.1f} h > 48 h (sledujte priemer, § 85 ods. 9 ZP)")

    # súhrn
    summary = defaultdict(float)
    abs_h = defaultdict(float)
    abs_days = defaultdict(float)
    abs_cal = defaultdict(int)
    for d, dd in dmap.items():
        summary["fond_h"] += dd.planned_h
        summary["covered_h"] += dd.covered_h
        if d < now.date():  # uzavreté dni (bez dneška)
            summary["fond_to_date_h"] += dd.planned_h
            summary["covered_to_date_h"] += dd.covered_h
            summary["worked_to_date_h"] += dd.worked_h + dd.holiday_paid_h
        summary["worked_h"] += dd.worked_h
        summary["night_h"] += dd.night_h
        summary["weekend_h"] += dd.weekend_h
        summary["holiday_h"] += dd.holiday_h
        summary["holiday_paid_h"] += dd.holiday_paid_h
        summary["auto_break_h"] += dd.auto_break_h
        summary["vacation_days"] += dd.vacation_days
        if dd.planned_h > 0:
            summary["plan_days"] += 1
        if dd.worked_h > 0:
            summary["worked_days"] += 1
        for k, v in dd.absences.items():
            abs_h[k] += v
        for code in dd.absence_cal:
            abs_cal[code] += 1
        for code in dd.absence_full:
            if code.endswith("/2"):
                abs_days[code[:-2]] += 0.5
            else:
                abs_days[code] += 1
        summary["warnings"] += len(dd.warnings)
    paid_abs = sum(v for k, v in abs_h.items() if types.get(k, {}).get("counts_as") == "paid")
    # odpracované už obsahuje neprítomnosti typu 'work' (služobná cesta, HO)
    summary["paid_absence_h"] = paid_abs
    # saldo = odpracované + ospravedlnené neprítomnosti + sviatok – fond (k dnešku aj za celý mesiac)
    summary["balance_h"] = summary["worked_h"] + summary["covered_h"] + summary["holiday_paid_h"] - summary["fond_h"]
    summary["balance_to_date_h"] = summary["worked_to_date_h"] + summary["covered_to_date_h"] - summary["fond_to_date_h"]
    summary["over_fond_h"] = max(summary["balance_h"], 0.0)
    res = {k: round(v, 2) for k, v in summary.items()}
    res["absence_h"] = {k: round(v, 2) for k, v in abs_h.items() if v}
    res["absence_days"] = {k: v for k, v in abs_days.items() if v}
    res["absence_cal_days"] = dict(abs_cal)
    return {"month": month, "days": [dmap[d].to_dict() for d in days], "summary": res}
