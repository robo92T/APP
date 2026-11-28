"""Indicative statutory premium minimums for 2026 (Slovakia).

Does NOT decide whether shift-day boundary exceptions, agreed lower weekend/night
rates, overtime or holiday compensatory time apply. The legal-monitor workflow
must be reviewed before accepting any new year's rates.
"""
from datetime import datetime,date,time,timedelta,timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from time_engine import attendance_intervals,split_minutes,normalize
from work_rules import expected_break,premium_amount
TZ=ZoneInfo("Europe/Bratislava")
RATES_2026={"night":Decimal("2.1036"),"saturday":Decimal("2.6295"),"sunday":Decimal("5.2590"),
            "night_risk":Decimal("2.6295")}
def accounted_intervals(events,employee,shift_map):
    raw,warnings=attendance_intervals(events)
    ordered=sorted((e for e in events if e.kind!="void"),key=lambda e:(normalize(e.at),getattr(e,"id",0)))
    sessions=[]
    arrival=None;explicit=False
    for event in ordered:
        at=normalize(event.at)
        if event.kind=="in":
            if arrival is None:arrival=at;explicit=False
        elif event.kind in ("break_start","break_end") and arrival is not None:
            explicit=True
        elif event.kind=="out" and arrival is not None:
            sessions.append((arrival,at,explicit))
            arrival=None;explicit=False
    result=[]
    for start,end,has_manual_break in sessions:
        if end<=start:continue
        pieces=[(max(a,start),min(b,end)) for a,b in raw if b>start and a<end]
        pieces=[(a,b) for a,b in pieces if b>a]
        if has_manual_break:
            result.extend(pieces)
            continue
        day=start.astimezone(TZ).date()
        shift=shift_map.get(day)
        regime=getattr(employee,"work_regime","fixed")
        if shift and (shift.start_time,shift.end_time,shift.planned_minutes) in (
            ("06:00","18:00",660),("18:00","06:00",660)):
            regime="dispatcher"
        deducted=expected_break(regime,start,end)
        if deducted<=0:
            result.extend(pieces)
            continue
        middle=start+(end-start)/2
        a=middle-timedelta(minutes=deducted//2)
        b=a+timedelta(minutes=deducted)
        for lo,hi in pieces:
            if b<=lo or a>=hi:result.append((lo,hi))
            else:
                if lo<a:result.append((lo,a))
                if b<hi:result.append((b,hi))
    return result,warnings

def summary(events,employee,shift_map,year,month,average_hourly=None,risk_night=False):
    if year!=2026:raise ValueError("Sadzby príplatkov na tento rok ešte nie sú overené")
    from calendar import monthrange
    start=date(year,month,1);end=date(year,month,monthrange(year,month)[1])
    intervals,warnings=accounted_intervals(events,employee,shift_map)
    mins=split_minutes(intervals,start,end)
    amounts={
        "night_eur":premium_amount(mins["night_minutes"],
                         RATES_2026["night_risk" if risk_night else "night"]),
        "saturday_eur":premium_amount(mins["saturday_minutes"],RATES_2026["saturday"]),
        "sunday_eur":premium_amount(mins["sunday_minutes"],RATES_2026["sunday"])}
    avg=Decimal(str(average_hourly)) if average_hourly is not None else None
    amounts["holiday_eur"]=premium_amount(mins["holiday_label_minutes"],avg) if avg is not None else None
    return {"period":f"{year}-{month:02d}","worked_min":mins["worked_minutes"],
        "night_min":mins["night_minutes"],"saturday_min":mins["saturday_minutes"],
        "sunday_min":mins["sunday_minutes"],"holiday_min":mins["holiday_label_minutes"],
        "amounts":{k:float(v) if v is not None else None for k,v in amounts.items()},
        "rates_eur_hour":{k:float(v) for k,v in RATES_2026.items()},
        "warnings":warnings+
          ["Orientačné zákonné minimá 2026 bez výnimiek a KZ; sviatok počíta 100 % priemerného zárobku, ak je uvedený.",
           "Sviatok môže mať náhradné voľno; nadčas, sťažený výkon, pohotovosť a dohody sa tu neoceňujú.",
           "Pri zmenných prevádzkach zákonný začiatok víkendu nemusí byť polnoc. Potvrď časové okná personálnym oddelením."],
        "note":"Nie je podklad na automatickú výplatu; vyžaduje potvrdenie mzdára."}
def install(app,Employee,Event,Shift,Base,db,require_role):
    @app.get("/api/premiums/{employee_id}",dependencies=[Depends(require_role("admin","hr"))])
    def premiums(employee_id:int,year:int=Query(ge=2026,le=2026),
                 month:int=Query(ge=1,le=12),average_hourly:float|None=Query(default=None,ge=0,le=10000),
                 risk_night:bool=False,session:Session=Depends(db)):
        e=session.get(Employee,employee_id)
        if not e:raise HTTPException(404,"Zamestnanec neexistuje")
        start=date(year,month,1);end=date(year,month,__import__("calendar").monthrange(year,month)[1])
        begin=datetime.combine(start-timedelta(days=2),time.min,TZ).astimezone(timezone.utc)
        stop=datetime.combine(end+timedelta(days=2),time.min,TZ).astimezone(timezone.utc)
        events=session.scalars(select(Event).where(Event.employee_id==employee_id,
            Event.at>=begin,Event.at<stop).order_by(Event.at,Event.id)).all()
        shifts={s.day:s for s in session.scalars(select(Shift).where(
            Shift.employee_id==employee_id,Shift.day>=start-timedelta(days=1),Shift.day<=end)).all()}
        profile=Base.metadata.tables.get("employee_profile")
        if profile is not None:
            val=session.execute(select(profile.c.work_regime).where(profile.c.employee_id==employee_id)).scalar_one_or_none()
            if val:e.work_regime=val
        return summary(events,e,shifts,year,month,average_hourly,risk_night)
