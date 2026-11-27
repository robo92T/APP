"""Exporty pre mzdový systém – konfigurovateľné profily (CSV / XLSX / XML / JSON).

Každý profil určuje: formát, úroveň (mesačný súhrn / denné riadky / riadky
neprítomností), oddeľovač, kódovanie, desatinný znak a zoznam stĺpcov
(pole -> názov stĺpca). Tak sa dá prispôsobiť importnej šablóne ľubovoľného
mzdového systému bez zmeny kódu.
"""
import csv
import io
import json
from xml.sax.saxutils import escape

MONTH_FIELDS = {
    "personal_number": "Osobné číslo", "last_name": "Priezvisko", "first_name": "Meno",
    "full_name": "Meno a priezvisko", "org_unit": "Útvar", "cost_center": "Stredisko",
    "fte": "Úväzok", "month": "Obdobie", "fond_h": "Fond (h)", "plan_days": "Plánované dni",
    "worked_days": "Odpracované dni", "worked_h": "Odpracované (h)", "night_h": "Nočná práca (h)",
    "weekend_h": "Sobota/nedeľa (h)", "holiday_h": "Práca vo sviatok (h)",
    "holiday_paid_h": "Sviatok – náhrada (h)", "paid_absence_h": "Platená neprítomnosť (h)",
    "balance_h": "Saldo voči fondu (h)", "over_fond_h": "Nad fond (h)",
    "vacation_days": "Dovolenka (dni)", "auto_break_h": "Automatická prestávka (h)",
}
DAY_FIELDS = {
    "personal_number": "Osobné číslo", "full_name": "Meno a priezvisko", "day": "Dátum",
    "shift": "Zmena", "planned_h": "Plán (h)", "first_in": "Príchod", "last_out": "Odchod",
    "worked_h": "Odpracované (h)", "night_h": "Nočná (h)", "weekend_h": "Víkend (h)",
    "holiday_h": "Sviatok (h)", "absences": "Neprítomnosti", "warnings": "Upozornenia",
}
ABSENCE_FIELDS = {
    "personal_number": "Osobné číslo", "full_name": "Meno a priezvisko", "month": "Obdobie",
    "code": "Kód", "payroll_code": "Mzdový kód", "name": "Druh", "days": "Pracovné dni", "cal_days": "Kalendárne dni", "hours": "Hodiny",
}


def build_rows(level, results, types):
    """results = [(emp, unit, calc_result)]"""
    out = []
    for emp, unit, res in results:
        base = {
            "personal_number": emp["personal_number"], "last_name": emp["last_name"],
            "first_name": emp["first_name"], "full_name": f'{emp["first_name"]} {emp["last_name"]}',
            "org_unit": unit.get("name") if unit else "", "cost_center": (unit or {}).get("cost_center") or "",
            "fte": emp["fte"], "month": res["month"],
        }
        s = res["summary"]
        if level == "month":
            r = dict(base)
            for k in MONTH_FIELDS:
                if k in s:
                    r[k] = s[k]
            for code, h in s.get("absence_h", {}).items():
                r[f"abs_h:{code}"] = h
            for code, d in s.get("absence_days", {}).items():
                r[f"abs_d:{code}"] = d
            for code, d in s.get("absence_cal_days", {}).items():
                r[f"abs_k:{code}"] = d
            out.append(r)
        elif level == "day":
            for d in res["days"]:
                r = dict(base)
                r.update({k: d.get(k) for k in ("day", "shift", "planned_h", "first_in", "last_out", "worked_h",
                                                  "night_h", "weekend_h", "holiday_h")})
                r["absences"] = ", ".join(f"{k}:{v}" for k, v in d["absences"].items())
                r["warnings"] = " | ".join(d["warnings"])
                for code, h in d["absences"].items():
                    r[f"abs_h:{code}"] = h
                out.append(r)
        elif level == "absence":
            codes = set(s.get("absence_h", {})) | set(s.get("absence_days", {})) | set(s.get("absence_cal_days", {}))
            for code in sorted(codes):
                t = types.get(code, {})
                r = dict(base)
                r.update({"code": code, "payroll_code": t.get("payroll_code") or code, "name": t.get("name", code),
                          "days": s.get("absence_days", {}).get(code, 0), "cal_days": s.get("absence_cal_days", {}).get(code, 0),
                          "hours": s.get("absence_h", {}).get(code, 0)})
                out.append(r)
    return out


def _fmt(v, decimal):
    if isinstance(v, float):
        s = f"{v:.2f}"
        return s.replace(".", decimal) if decimal != "." else s
    return "" if v is None else str(v)


def render(profile, rows):
    cols = json.loads(profile["columns"]) if isinstance(profile["columns"], str) else profile["columns"]
    fmt = profile["fmt"]
    dec = profile.get("decimal") or ","
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=profile.get("delimiter") or ";", lineterminator="\r\n")
        w.writerow([c["header"] for c in cols])
        for r in rows:
            w.writerow([_fmt(r.get(c["field"], 0 if c["field"].startswith("abs_") else ""), dec) for c in cols])
        enc = profile.get("encoding") or "utf-8-sig"
        return buf.getvalue().encode(enc, errors="replace"), "text/csv", "csv"
    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Dochádzka"
        ws.append([c["header"] for c in cols])
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="0B2D5B")
        for r in rows:
            ws.append([r.get(c["field"], 0 if c["field"].startswith("abs_") else None) for c in cols])
        for i, c in enumerate(cols, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = max(12, len(c["header"]) + 2)
        ws.freeze_panes = "A2"
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    if fmt == "xml":
        parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<Dochadzka>"]
        for r in rows:
            parts.append("  <Zaznam>")
            for c in cols:
                tag = "".join(ch for ch in c["header"] if ch.isalnum()) or c["field"].replace(":", "_")
                v = r.get(c["field"], 0 if c["field"].startswith("abs_") else "")
                parts.append(f"    <{tag}>{escape(_fmt(v, '.'))}</{tag}>")
            parts.append("  </Zaznam>")
        parts.append("</Dochadzka>")
        return "\n".join(parts).encode("utf-8"), "application/xml", "xml"
    data = [{c["header"]: r.get(c["field"], 0 if c["field"].startswith("abs_") else None) for c in cols} for r in rows]
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"), "application/json", "json"
