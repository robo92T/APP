"""Aktion-style staff attendance overview (daily and monthly), read-only and HR-scoped.

Shows measured time, attendance labels, department and approved absence components,
without representing provisional balances as certified payroll amounts.
"""
import csv
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO, StringIO
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from time_engine import calculate
from pdf_reports import build_rows

TZ=ZoneInfo("Europe/Bratislava")
ABSENCE_LABELS={
    "vacation":"Dovolenka","doctor":"Lekár","accompany":"Sprevádzanie",
    "doctor_unpaid":"Lekár – neplatené","accompany_unpaid":"Sprevádzanie – neplatené",
    "sick":"PN","ocr":"OČR","maternity":"Materská dovolenka","paternity":"Otcovská dovolenka",
    "parental":"Rodičovská dovolenka","unpaid":"Neplatené voľno",
    "paid_leave":"Platené voľno","business_trip":"Pracovná cesta",
    "home_office":"Home office","training":"Školenie","wedding":"Svadba","funeral":"Pohreb",
    "blood_donation":"Darovanie krvi","other":"Iná neprítomnosť"
}
DAY_HEADERS=[
    ("date","Dátum"),("personal_number","Os. číslo"),("name","Meno a priezvisko"),
    ("department","Útvar"),("job_title","Pracovná pozícia"),("status","Stav"),
    ("first_in","Príchod"),("last_out","Odchod"),("last_punch","Posledný záznam"),
    ("planned_min","Fond (min)"),("worked_min","Odpracované (min)"),
    ("break_min","Prestávky (min)"),("credited_min","Uznané voľno (min)"),
    ("saldo_min","Saldo (min)"),("component","Zložka / neprítomnosť"),
    ("warnings","Upozornenia")]
MONTH_HEADERS=[
    ("personal_number","Os. číslo"),("name","Meno a priezvisko"),
    ("department","Útvar"),("job_title","Pracovná pozícia"),
    ("presence","Aktuálny stav"),("planned_min","Fond (min)"),
    ("worked_min","Odpracované (min)"),("break_min","Prestávky (min)"),
    ("credited_min","Uznané voľno (min)"),("saldo_min","Saldo (min)"),
    ("vacation_min","Dovolenka (min)"),("doctor_min","Lekár (min)"),
    ("accompany_min","Sprevádzanie (min)"),
    ("other_absence_min","Ostatné voľno (min)"),
    ("night_min","Nočné (min)"),("saturday_min","Sobota (min)"),
    ("sunday_min","Nedeľa (min)"),("holiday_min","Sviatok (min)"),
    ("attendance_days","Dni s prácou"),("warnings","Upozornenia")]
def valid_period(mode, day, year,month):
    if mode not in ("day","month"):raise HTTPException(422,"Neplatný režim")
    if mode=="day":
        return day.year,day.month,day
    if not 2020<=year<=2100 or not 1<=month<=12:
        raise HTTPException(422,"Neplatný mesiac")
    return year,month,None

def utc_time(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def state_for_date(events,asof):
    """RFID event-based state, NOT proof of physical presence in a building."""
    last=None
    for event in events:
        at=utc_time(event.at)
        if at<=asof and event.kind!="void":last=event
    if last is None:return "unknown",None
    if last.kind in ("in","break_end"):return "present",utc_time(last.at)
    if last.kind=="break_start":return "break",utc_time(last.at)
    return "away",utc_time(last.at)

def install(app,Employee,Event,Absence,Shift,Base,db,require_role):
    from time_engine import calculate
    @app.get("/api/group-report",dependencies=[Depends(require_role("admin","hr"))])
    def group_report(mode:str="day",
          day:date=Query(default_factory=date.today),
          year:int=Query(default_factory=lambda:date.today().year),
          month:int=Query(default_factory=lambda:date.today().month),
          session:Session=Depends(db)):
        yy,mm,chosen=valid_period(mode,day,year,month)
        begin=date(yy,mm,1)
        finish=date(yy,mm,monthrange(yy,mm)[1])
        target=chosen or date.today()
        period_start=chosen if chosen else begin
        period_end=chosen if chosen else finish
        # Include prior punches, across-midnight arrivals, and future-day exits for row splitting.
        earliest=datetime.combine(begin-timedelta(days=2),time.min,TZ).astimezone(timezone.utc)
        latest=datetime.combine(finish+timedelta(days=2),time.min,TZ).astimezone(timezone.utc)
        profiles_table=Base.metadata.tables.get("employee_profile")
        membership_table=Base.metadata.tables.get("org_membership")
        org_table=Base.metadata.tables.get("org_unit")
        profile_map={}
        if profiles_table is not None:
            profile_map={r["employee_id"]:r for r in session.execute(
                select(profiles_table)
            ).mappings().all()}
        department_map={}
        if org_table is not None and membership_table is not None:
            names={r["id"]:r["name"] for r in session.execute(select(org_table)).mappings().all()}
            for row in session.execute(select(membership_table)).mappings().all():
                department_map[row["employee_id"]]=names.get(row["unit_id"],"")
        employees=session.scalars(select(Employee).order_by(Employee.name)).all()
        employee_ids=[e.id for e in employees]
        all_events=session.scalars(select(Event).where(
            Event.employee_id.in_(employee_ids),Event.at>=earliest,
            Event.at<latest).order_by(Event.employee_id,Event.at,Event.id)).all() if employees else []
        all_absences=session.scalars(select(Absence).where(
            Absence.employee_id.in_(employee_ids),Absence.start<=period_end,
            Absence.end>=period_start).order_by(Absence.employee_id,Absence.start)).all() if employees else []
        all_shifts=session.scalars(select(Shift).where(
            Shift.employee_id.in_(employee_ids),
            Shift.day>=begin-timedelta(days=1),Shift.day<=finish)).all() if employees else []
        from collections import defaultdict
        events_by=defaultdict(list);absences_by=defaultdict(list);shifts_by=defaultdict(dict)
        for e in all_events:events_by[e.employee_id].append(e)
        for a in all_absences:absences_by[a.employee_id].append(a)
        for shift in all_shifts:shifts_by[shift.employee_id][shift.day]=shift
        travel_dates=set()
        travel_table=Base.metadata.tables.get("travel_order")
        if travel_table is not None:
            for trip in session.execute(select(travel_table).where(
                travel_table.c.status=="approved")).mappings().all():
                start=utc_time(trip["starts_at"]).astimezone(TZ).date()
                end=utc_time(trip["ends_at"]).astimezone(TZ).date()
                day_cursor=max(start,period_start)
                while day_cursor<=min(end,period_end):
                    travel_dates.add((trip["employee_id"],day_cursor))
                    day_cursor+=timedelta(days=1)
        report_rows=[]
        counts={"total":0,"present":0,"break":0,"absent":0,"away":0,"unrecorded":0,"warning":0}
        now=datetime.now(timezone.utc)
        current_day=datetime.now(TZ).date()
        status_asof=datetime.combine(target+timedelta(days=1),time.min,TZ).astimezone(timezone.utc)
        if target>=current_day:status_asof=now
        for person in employees:
            if person.start_date>period_end or (person.end_date and person.end_date<period_start):continue
            if not person.active and mode=="day" and target==current_day:continue
            profile=profile_map.get(person.id,{})
            common={"employee_id":person.id,"personal_number":profile.get("personal_number",str(person.id)),
                "name":person.name,"department":department_map.get(person.id) or profile.get("department",""),
                "job_title":profile.get("job_title",""),"fte":profile.get("fte",1),
                "work_regime":profile.get("work_regime","fixed")}
            records=events_by[person.id]
            absence_list=absences_by[person.id]
            confirmed=[a for a in absence_list if a.status=="approved"]
            daily=build_rows(person,records,shifts_by[person.id],confirmed,yy,mm)
            if mode=="day":
                r=next((x for x in daily if x["day"]==target),None)
                if r is None:continue
                interval_end=status_asof
                last_punches=[e for e in records if utc_time(e.at)<=interval_end and e.kind!="void"]
                latest_punch=last_punches[-1] if last_punches else None
                today_absences=[a for a in absence_list if a.start<=target<=a.end and a.status=="approved"]
                absent_labels=[ABSENCE_LABELS.get(a.kind,a.kind) for a in today_absences]
                is_current=target==current_day
                state,last_state_at=state_for_date(last_punches,interval_end)
                # For historical days, a finished punch does not imply "in the office now".
                if not is_current:
                    state="history"
                on_trip=(person.id,target) in travel_dates
                if on_trip:
                    status="Služobná cesta";key="absent"
                elif absent_labels:
                    status="Neprítomnosť"
                    key="absent"
                elif is_current and state=="present":
                    status="Na pracovisku*";key="present"
                elif is_current and state=="break":
                    status="Prestávka*";key="break"
                elif is_current and state=="away":
                    status="Mimo pracoviska*";key="away"
                elif r["worked"]>0:
                    status="Odpracované";key="away"
                elif r["warnings"]:
                    status="Vyžaduje kontrolu";key="unrecorded"
                else:
                    status="Bez záznamu";key="unrecorded"
                pending=[a for a in absence_list if a.start<=target<=a.end and a.status=="pending"]
                if pending and not absent_labels:status="Žiadosť čaká";key="unrecorded"
                warning=list(r["warnings"])
                if is_current and state in ("present","break"):
                    warning.append("Otvorená zmena: odpracovaný čas zatiaľ nezahŕňa otvorený interval")
                out={**common,"date":target.isoformat(),"status":status,"status_key":key,
                    "first_in":r["in"].astimezone(TZ).strftime("%H:%M") if r["in"] else None,
                    "last_out":r["out"].astimezone(TZ).strftime("%H:%M") if r["out"] else None,
                    "last_punch":utc_time(latest_punch.at).astimezone(TZ).strftime("%H:%M") if latest_punch else None,
                    "last_kind":latest_punch.kind if latest_punch else None,
                    "planned_min":r["plan"],"worked_min":r["worked"],
                    "break_min":r["breaks"],"credited_min":r["credit"],
                    "saldo_min":r["saldo"],"component":"Služobná cesta" if on_trip else ", ".join(absent_labels) if absent_labels else ("Práca" if r["worked"] else "—"),
                    "warnings":warning}
                report_rows.append(out)
                counts[key]+=1;counts["total"]+=1
                if warning:counts["warning"]+=1
            else:
                totals={key:sum(r[key] for r in daily) for key in ("plan","worked","breaks","credit","saldo")}
                category=calculate(records,begin,finish)
                component_minutes=defaultdict(int)
                for r in daily:
                    for part in r["absence"].split(", "):
                        if part:component_minutes[part]+=r["credit"]
                presence_events=[e for e in records if utc_time(e.at)<=now and e.kind!="void"]
                state,_=state_for_date(presence_events,now)
                today_absences=[a for a in confirmed if a.start<=current_day<=a.end]
                on_trip_today=(person.id,current_day) in travel_dates
                presence=", ".join(ABSENCE_LABELS.get(a.kind,a.kind) for a in today_absences) if today_absences else ("Príchod otvorený*" if state=="present" else "Mimo / bez otvoreného príchodu")
                if on_trip_today:presence="Služobná cesta"
                elif any(a.kind=="home_office" for a in today_absences):presence="Home office"
                warnings=sum(len(r["warnings"]) for r in daily)+len(category["warnings"])
                out={**common,"presence":presence,
                    "planned_min":totals["plan"],"worked_min":totals["worked"],
                    "break_min":totals["breaks"],"credited_min":totals["credit"],
                    "saldo_min":totals["saldo"],
                    "vacation_min":component_minutes["vacation"],"doctor_min":component_minutes["doctor"],
                    "accompany_min":component_minutes["accompany"],
                    "other_absence_min":sum(v for k,v in component_minutes.items() if k not in ("vacation","doctor","accompany")),
                    "night_min":category["night_minutes"],
                    "saturday_min":category["saturday_minutes"],
                    "sunday_min":category["sunday_minutes"],
                    "holiday_min":category["holiday_label_minutes"],
                    "attendance_days":sum(r["worked"]>0 for r in daily),
                    "warnings":warnings}
                report_rows.append(out)
                counts["total"]+=1
                counts["warning"]+=int(warnings>0)
        if mode=="day":
            totals={key:sum(r[key] for r in report_rows) for key in ("planned_min","worked_min","break_min","credited_min","saldo_min")}
        else:
            totals={key:sum(r[key] for r in report_rows) for key in ("planned_min","worked_min","break_min","credited_min","saldo_min","vacation_min","doctor_min","accompany_min","night_min")}
        return {"mode":mode,"date":target.isoformat() if mode=="day" else None,
            "year":yy,"month":mm,"columns":[{"key":k,"label":label} for k,label in (DAY_HEADERS if mode=="day" else MONTH_HEADERS)],
            "rows":report_rows,"counts":counts,"totals":totals,"as_of":now.isoformat(),
            "note":"* Prítomnosť je orientačne odvodená z posledného RFID záznamu, nie z fyzickej lokalizácie. Otvorené zmeny nie sú v odpracovanom čase. Saldo a neprítomnosti treba pred mzdami skontrolovať."}

    @app.get("/api/group-report/export",dependencies=[Depends(require_role("admin","hr"))])
    def export(mode:str="day",day:date=Query(default_factory=date.today),
               year:int=Query(default_factory=lambda:date.today().year),
               month:int=Query(default_factory=lambda:date.today().month),
               file_format:str="csv",session:Session=Depends(db)):
        if file_format not in ("csv","xlsx"):raise HTTPException(422,"Podporované sú CSV a XLSX")
        data=group_report(mode,day,year,month,session)
        cols=data["columns"];rows=data["rows"];totals=data["totals"]
        stamp=day.isoformat() if mode=="day" else f"{year}-{month:02d}"
        name=f"bid_hromadna_dochadzka_{mode}_{stamp}.{file_format}"
        if file_format=="csv":
            out=StringIO();writer=csv.writer(out,delimiter=";",lineterminator="\r\n")
            writer.writerow([c["label"] for c in cols])
            for row in rows:
                writer.writerow([safe_csv(row.get(c["key"],"")) for c in cols])
            payload=("\ufeff"+out.getvalue()).encode("utf-8")
            typ="text/csv; charset=utf-8"
        else:
            import xlsxwriter
            output=BytesIO();workbook=xlsxwriter.Workbook(output,{"in_memory":True,"strings_to_formulas":False,"strings_to_urls":False})
            sheet=workbook.add_worksheet("Hromadný výkaz")
            header=workbook.add_format({"bold":True,"bg_color":"#13365F","font_color":"white","text_wrap":True})
            number=workbook.add_format({"num_format":"0"})
            for c,col in enumerate(cols):sheet.write_string(0,c,col["label"],header)
            for i,row in enumerate(rows,1):
                for j,col in enumerate(cols):
                    value=row.get(col["key"],"")
                    if isinstance(value,(int,float)):sheet.write_number(i,j,value,number)
                    elif isinstance(value,list):sheet.write_string(i,j,"; ".join(value))
                    else:sheet.write_string(i,j,str(value or ""))
            sheet.freeze_panes(1,2);sheet.autofilter(0,0,max(1,len(rows)),max(0,len(cols)-1))
            sheet.set_column(0,1,18);sheet.set_column(2,len(cols)-1,17)
            workbook.close();payload=output.getvalue()
            typ="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return StreamingResponse(iter([payload]),media_type=typ,headers={"Cache-Control":"no-store",
            "Content-Disposition":f'attachment; filename="{name}"'})

def safe_csv(value):
    if isinstance(value,list):value="; ".join(str(x) for x in value)
    if isinstance(value,str) and value.startswith(("=","+","-","@","\t","\r")):return "'"+value
    return value if value is not None else ""
