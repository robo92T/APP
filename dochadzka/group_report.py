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
from wage_components import get_mode_minutes,KINDS as WAGE_KINDS,PAYROLL_CREDIT_KINDS

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
    ("saldo_min","Saldo (min)"),("doctor_min","Lekár (min)"),
    ("accompany_min","Sprevádzanie (min)"),("home_office_min","Home office (min)"),
    ("business_trip_min","Služobná cesta (min)"),("service_errand_min","Služobné dôvody (min)"),
    ("travel_duration_min","Trvanie cesty (min)"),
    ("vacation_min","Dovolenka (min)"),("sick_min","PN (min)"),("ocr_min","OČR (min)"),
    ("doctor_unpaid_min","Lekár – neplatené (min)"),("accompany_unpaid_min","Sprevádzanie – neplatené (min)"),
    ("maternity_min","Materská dovolenka (min)"),("paternity_min","Otcovská dovolenka (min)"),
    ("parental_min","Rodičovská dovolenka (min)"),("unpaid_min","Neplatené voľno (min)"),
    ("paid_leave_min","Platené voľno (min)"),("training_min","Školenie (min)"),
    ("wedding_min","Svadba (min)"),("funeral_min","Pohreb (min)"),
    ("blood_donation_min","Darovanie krvi (min)"),("other_min","Iná neprítomnosť (min)"),
    ("component","Zložka / neprítomnosť"),
    ("warnings","Upozornenia")]
MONTH_HEADERS=[
    ("personal_number","Os. číslo"),("name","Meno a priezvisko"),
    ("department","Útvar"),("job_title","Pracovná pozícia"),
    ("presence","Aktuálny stav"),("planned_min","Fond (min)"),
    ("worked_min","Odpracované (min)"),("break_min","Prestávky (min)"),
    ("credited_min","Uznané voľno (min)"),("saldo_min","Saldo (min)"),
    ("vacation_min","Dovolenka (min)"),("doctor_min","Lekár (min)"),
    ("accompany_min","Sprevádzanie (min)"),
    ("home_office_min","Home office (min)"),("business_trip_min","Služobná cesta (min)"),
    ("service_errand_min","Služobné dôvody (min)"),("travel_duration_min","Trvanie cesty (min)"),
    ("other_absence_min","Ostatné voľno (min)"),
    ("night_min","Nočné (min)"),("saturday_min","Sobota (min)"),
    ("sunday_min","Nedeľa (min)"),("holiday_min","Sviatok (min)"),
    ("attendance_days","Dni s prácou"),
    ("sick_min","PN (min)"),("ocr_min","OČR (min)"),
    ("doctor_unpaid_min","Lekár – neplatené (min)"),("accompany_unpaid_min","Sprevádzanie – neplatené (min)"),
    ("maternity_min","Materská dovolenka (min)"),("paternity_min","Otcovská dovolenka (min)"),
    ("parental_min","Rodičovská dovolenka (min)"),("unpaid_min","Neplatené voľno (min)"),
    ("paid_leave_min","Platené voľno (min)"),("training_min","Školenie (min)"),
    ("wedding_min","Svadba (min)"),("funeral_min","Pohreb (min)"),
    ("blood_donation_min","Darovanie krvi (min)"),("other_min","Iná neprítomnosť (min)"),
    ("warnings","Upozornenia")]
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

def install(app,Employee,Event,Absence,Shift,WageComponent,Base,db,require_role):
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
        travel_minutes=defaultdict(int)
        travel_table=Base.metadata.tables.get("travel_order")
        if travel_table is not None:
            for trip in session.execute(select(travel_table).where(
                travel_table.c.status=="approved")).mappings().all():
                start_utc=utc_time(trip["starts_at"])
                end_utc=utc_time(trip["ends_at"])
                if end_utc<=start_utc:continue
                day_cursor=max(start_utc.astimezone(TZ).date(),period_start)
                last_day=min(end_utc.astimezone(TZ).date(),period_end)
                while day_cursor<=last_day:
                    travel_dates.add((trip["employee_id"],day_cursor))
                    lo=max(start_utc,datetime.combine(day_cursor,time.min,TZ).astimezone(timezone.utc))
                    hi=min(end_utc,datetime.combine(day_cursor+timedelta(days=1),time.min,TZ).astimezone(timezone.utc))
                    travel_minutes[(trip["employee_id"],day_cursor)]+=max(0,int((hi-lo).total_seconds()//60))
                    day_cursor+=timedelta(days=1)
        components_by=defaultdict(lambda:defaultdict(list))
        for comp in session.scalars(select(WageComponent).where(
            WageComponent.day>=period_start,WageComponent.day<=period_end,
            WageComponent.active==True)).all():
            components_by[comp.employee_id][comp.day].append(comp)
        PAID_KINDS={"vacation","doctor","accompany","paid_leave","wedding",
            "funeral","blood_donation"}
        WORK_KINDS={"business_trip","service_errand","home_office","training"}
        ALL_COMPONENT_KINDS=set(ABSENCE_LABELS)|{"service_errand"}
        def classify_day(employee_id,raw,approved_absences):
            day=raw["day"];plan=raw["plan"];punched=raw["worked"]
            values={kind+"_min":0 for kind in ALL_COMPONENT_KINDS}
            values["travel_duration_min"]=travel_minutes.get((employee_id,day),0)
            warnings=[]
            work_add=0
            remaining=max(0,plan-punched)
            paid_add=0
            # A confirmed HR business trip/training absence is treated as a work
            # assignment for that day; PN/OČR are separately tracked but never
            # classified as worked or paid-credit time.
            for absence in approved_absences:
                if not absence.start<=day<=absence.end:continue
                amount=max(0,int(absence.minutes)) if absence.minutes is not None and absence.start==absence.end else plan
                key=absence.kind+"_min"
                if key not in values:continue
                if absence.kind=="home_office":
                    values[key]=max(values[key],punched)
                elif absence.kind in ("business_trip","training"):
                    add=min(amount,remaining)
                    values[key]+=add
                    work_add+=add;remaining-=add
                    if punched and amount:warnings.append("Čas pracovnej cesty/školenia môže prekrývať pípnutia – over HR")
                elif absence.kind in PAID_KINDS:
                    add=min(amount,remaining)
                    values[key]+=add
                    paid_add+=add;remaining-=add
                else:
                    # PN, OČR, rodičovská atď. are measured as absence,
                    # not a worked hour and not ordinary paid leave.
                    values[key]=max(values[key],amount)
            selected=components_by.get(employee_id,{}).get(day,[])
            labels=[]
            for comp in selected:
                labels.append(WAGE_KINDS.get(comp.kind,comp.kind))
                amount=get_mode_minutes(comp,plan,punched)
                key=comp.kind+"_min"
                if comp.mode=="punched":
                    # Punch-based categorization is a subset of already
                    # recorded work. No additional minutes to total work.
                    if comp.kind in WORK_KINDS:values[key]=max(values[key],punched)
                    else:
                        values[key]=max(values[key],min(plan,amount))
                    continue
                if comp.kind in WORK_KINDS:
                    add=min(amount,remaining)
                    # A second manual entry supplements already classified
                    # worked minutes but never creates extra hours beyond fund.
                    values[key]+=add
                    work_add+=add;remaining-=add
                    if punched and amount:warnings.append("Mzdový čas môže prekrývať pípnutia; vyžaduje kontrolu")
                elif comp.kind in PAID_KINDS:
                    add=min(amount,remaining)
                    values[key]+=add
                    paid_add+=add;remaining-=add
                else:
                    values[key]=max(values[key],amount)
            if (employee_id,day) in travel_dates and not values["business_trip_min"]:
                warnings.append("Evidovaná cesta: iba trvanie, bez schváleného pracovného času; doplň mzdovú zložku")
            # No category is counted twice toward the attendance balance.
            return values,work_add,paid_add,", ".join(labels) if labels else None,warnings
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
                # Only a recent event can indicate current presence. An old
                # open "in" must not show every employee as on site on Saturday.
                recent_cutoff=datetime.combine(target,time.min,TZ).astimezone(timezone.utc)-timedelta(hours=12)
                last_punches=[e for e in records if recent_cutoff<=utc_time(e.at)<=interval_end and e.kind!="void"]
                latest_punch=last_punches[-1] if last_punches else None
                today_absences=[a for a in absence_list if a.start<=target<=a.end and a.status=="approved"]
                absent_labels=[ABSENCE_LABELS.get(a.kind,a.kind) for a in today_absences]
                is_current=target==current_day
                state,last_state_at=state_for_date(last_punches,interval_end)
                if state in ("present","break") and last_state_at and (interval_end-last_state_at)>timedelta(hours=14):
                    state="unknown"
                # For historical days, a finished punch does not imply "in the office now".
                if not is_current:
                    state="history"
                on_trip=(person.id,target) in travel_dates
                is_ho=any(a.kind=="home_office" for a in today_absences)
                if on_trip:
                    status="Služobná cesta";key="absent"
                elif is_ho:
                    status="Home office – práca" if r["worked"]>0 else "Home office – čaká na výkaz"
                    key="present" if r["worked"]>0 else "unrecorded"
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
                wage_values,extra_work,paid_credit,wage_kind,wage_warnings=classify_day(person.id,r,today_absences)
                warning=list(r["warnings"])+wage_warnings
                selected_kinds=[x.kind for x in components_by.get(person.id,{}).get(target,[])]
                if selected_kinds and not on_trip and not is_ho and not today_absences:
                    if all(k in ("doctor","accompany") for k in selected_kinds):
                        status="Lekár / sprevádzanie";key="absent"
                    elif "service_errand" in selected_kinds:
                        status="Služobné dôvody";key="away"
                    elif "business_trip" in selected_kinds:
                        status="Služobná cesta";key="absent"
                    elif "home_office" in selected_kinds:
                        status="Home office";key="present" if r["worked"] else "unrecorded"
                if is_current and state in ("present","break"):
                    warning.append("Otvorená zmena: odpracovaný čas zatiaľ nezahŕňa otvorený interval")
                out={**common,"date":target.isoformat(),"status":status,"status_key":key,
                    "first_in":r["in"].astimezone(TZ).strftime("%H:%M") if r["in"] else None,
                    "last_out":r["out"].astimezone(TZ).strftime("%H:%M") if r["out"] else None,
                    "last_punch":utc_time(latest_punch.at).astimezone(TZ).strftime("%H:%M") if latest_punch else None,
                    "last_kind":latest_punch.kind if latest_punch else None,
                    "planned_min":r["plan"],"worked_min":r["worked"]+extra_work,
                    "break_min":r["breaks"],"credited_min":paid_credit,
                    "saldo_min":r["worked"]+extra_work+paid_credit-r["plan"],**wage_values,
                    "component":wage_kind if wage_kind else "Služobná cesta" if on_trip else "Home office" if is_ho else ", ".join(absent_labels) if absent_labels else ("Práca" if r["worked"] else "—"),
                    "warnings":warning}
                report_rows.append(out)
                counts[key]+=1;counts["total"]+=1
                if warning:counts["warning"]+=1
            else:
                category=calculate(records,begin,finish)
                component_minutes=defaultdict(int)
                worked_total=0;credit_total=0;plan_total=0
                component_warnings=[]
                attendance_days=0
                for r in daily:
                    values,extra_work,credit,kind,warnings=classify_day(person.id,r,confirmed)
                    for key,value in values.items():component_minutes[key]+=value
                    worked_total+=r["worked"]+extra_work
                    credit_total+=credit
                    plan_total+=r["plan"]
                    attendance_days+=int(r["worked"]+extra_work>0)
                    component_warnings.extend(warnings)
                presence_events=[e for e in records if utc_time(e.at)<=now and e.kind!="void"]
                state,_=state_for_date(presence_events,now)
                today_absences=[a for a in confirmed if a.start<=current_day<=a.end]
                on_trip_today=(person.id,current_day) in travel_dates
                presence=", ".join(ABSENCE_LABELS.get(a.kind,a.kind) for a in today_absences) if today_absences else ("Príchod otvorený*" if state=="present" else "Mimo / bez otvoreného príchodu")
                if on_trip_today:presence="Služobná cesta"
                elif any(a.kind=="home_office" for a in today_absences):presence="Home office"
                warnings=sum(len(r["warnings"]) for r in daily)+len(category["warnings"])+len(component_warnings)
                out={**common,"presence":presence,
                    "planned_min":plan_total,"worked_min":worked_total,
                    "break_min":sum(r["breaks"] for r in daily),"credited_min":credit_total,
                    "saldo_min":worked_total+credit_total-plan_total,
                    "vacation_min":component_minutes["vacation_min"],
                    "doctor_min":component_minutes["doctor_min"],
                    "accompany_min":component_minutes["accompany_min"],
                    "home_office_min":component_minutes["home_office_min"],
                    "business_trip_min":component_minutes["business_trip_min"],
                    "service_errand_min":component_minutes["service_errand_min"],
                    "travel_duration_min":component_minutes["travel_duration_min"],
                    "other_absence_min":sum(component_minutes[k+"_min"] for k in ("unpaid","other","doctor_unpaid","accompany_unpaid")),
                    **{k+"_min":component_minutes[k+"_min"] for k in ALL_COMPONENT_KINDS if k not in
                        ("doctor","accompany","home_office","business_trip","service_errand","vacation")},
                    "night_min":category["night_minutes"],
                    "saturday_min":category["saturday_minutes"],
                    "sunday_min":category["sunday_minutes"],
                    "holiday_min":category["holiday_label_minutes"],
                    "attendance_days":attendance_days,
                    "warnings":warnings}
                report_rows.append(out)
                counts["total"]+=1
                counts["warning"]+=int(warnings>0)
        if mode=="day":
            totals={key:sum(r[key] for r in report_rows) for key in ("planned_min","worked_min","break_min","credited_min","saldo_min")}
        else:
            totals={key:sum(r[key] for r in report_rows) for key in ("planned_min","worked_min","break_min","credited_min","saldo_min","vacation_min","doctor_min","accompany_min","home_office_min","business_trip_min","service_errand_min","travel_duration_min","night_min")}
        return {"mode":mode,"date":target.isoformat() if mode=="day" else None,
            "year":yy,"month":mm,"columns":[{"key":k,"label":label} for k,label in (DAY_HEADERS if mode=="day" else MONTH_HEADERS)],
            "rows":report_rows,"counts":counts,"totals":totals,"as_of":now.isoformat(),
            "note":"Odpracované = dokončené pípnutia + schválená pracovná klasifikácia cesty, služobného vybavovania alebo práce z domu (bez duplicít). Lekár, sprevádzanie a platené voľno dopĺňajú fond samostatne. PN, OČR a neplatené voľno sú neprítomnosti, nie odpracované hodiny. Finálne mzdové exporty ešte vyžadujú zosúladenie a HR kontrolu."}

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
