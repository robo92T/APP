"""Attendance quality and Slovak Working Code reference checks.

Warnings only; definitive §85, §91, §92 and §97 compliance depends on
applicable schedule, agreed exceptions and full averaging period.
"""
from datetime import datetime,date,time,timedelta,timezone
from collections import defaultdict
from zoneinfo import ZoneInfo
from fastapi import Depends,HTTPException,Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from time_engine import normalize,calculate
TZ=ZoneInfo("Europe/Bratislava")

def inspect(events,regime="fixed"):
    items=sorted(events,key=lambda e:(normalize(e.at),getattr(e,"id",0)))
    warnings=[]
    shifts=[]
    open_at=None;pause_start=None;pause_minutes=0
    for e in items:
        at=normalize(e.at)
        if e.kind=="in":
            if open_at is not None:
                warnings.append({"at":at.isoformat(),"code":"DOUBLE_IN","message":"Dvojitý príchod"})
            else:open_at=at;pause_start=None;pause_minutes=0
        elif e.kind=="break_start":
            if open_at is not None and pause_start is None:pause_start=at
        elif e.kind=="break_end":
            if pause_start is not None:
                pause_minutes+=max(0,int((at-pause_start).total_seconds()//60))
                pause_start=None
        elif e.kind=="out":
            if open_at is None:
                warnings.append({"at":at.isoformat(),"code":"OUT_WITHOUT_IN","message":"Odchod bez príchodu"})
            else:
                if pause_start is not None:pause_minutes+=max(0,int((at-pause_start).total_seconds()//60))
                gross=int((at-open_at).total_seconds()//60)
                shifts.append((open_at,at,pause_minutes,max(0,gross-pause_minutes)))
                open_at=None;pause_start=None;pause_minutes=0
    if open_at is not None:
        warnings.append({"at":open_at.isoformat(),"code":"OPEN_SHIFT","message":"Neukončený príchod"})
    week=defaultdict(int)
    last_end=None
    for start,end,break_min,worked in shifts:
        local=start.astimezone(TZ)
        if last_end is not None:
            rest=(start-last_end).total_seconds()/3600
            limit=8 if regime in ("rotating","continuous") else 12
            if rest<limit:
                warnings.append({"at":local.isoformat(),"code":"REST_TOO_SHORT",
                    "message":f"Odpočinok {rest:.1f} h; referenčne aspoň {limit} h. Over výnimky."})
            elif rest<12:
                warnings.append({"at":local.isoformat(),"code":"REST_EXCEPTION",
                    "message":f"Odpočinok {rest:.1f} h – over zákonnú výnimku a náhradu odpočinku."})
        last_end=end
        gross=(end-start).total_seconds()/3600
        if gross>12:
            warnings.append({"at":local.isoformat(),"code":"SHIFT_OVER_12",
                "message":"Smena dlhšia ako 12 hodín – vyžaduje kontrolu rozvrhu."})
        if gross>6 and break_min<30 and regime not in ("rotating","continuous"):
            warnings.append({"at":local.isoformat(),"code":"BREAK_MISSING",
                "message":"Smena nad 6 h bez evidovanej 30-minútovej prestávky."})
        if regime in ("rotating","continuous") and break_min==0 and gross>6:
            warnings.append({"at":local.isoformat(),"code":"PAID_BREAK_VERIFY",
                "message":"Over, či zamestnanec pracuje bez prerušenia a prestávka sa započítava podľa § 91 ods. 5."})
        year,week,_=local.isocalendar()
        week_key=f"{year}-W{week:02d}"
        week[week_key]+=worked
    for key,minutes in week.items():
        if minutes>48*60:
            warnings.append({"at":key,"code":"WEEK_OVER_48",
                "message":"Odpracovaných viac ako 48 h za týždeň; over priemer vo vyrovnávacom období."})
    return {"shifts":len(shifts),"warnings":warnings,"week_minutes":dict(week)}

def install(app,Employee,Event,Base,db,require_role):
    @app.get("/api/quality/monthly",dependencies=[Depends(require_role("admin","hr"))])
    def monthly(year:int=Query(ge=2020,le=2100),month:int=Query(ge=1,le=12),session:Session=Depends(db)):
        from calendar import monthrange
        first=date(year,month,1);last=date(year,month,monthrange(year,month)[1])
        start=datetime.combine(first-timedelta(days=2),time.min,TZ).astimezone(timezone.utc)
        stop=datetime.combine(last+timedelta(days=2),time.min,TZ).astimezone(timezone.utc)
        ptable=Base.metadata.tables.get("employee_profile")
        regimes={}
        if ptable is not None:
            for eid,regime in session.execute(select(ptable.c.employee_id,ptable.c.work_regime)).all():
                regimes[eid]=regime
        findings=[]
        for employee in session.scalars(select(Employee).where(Employee.active==True)).all():
            punches=session.scalars(select(Event).where(Event.employee_id==employee.id,
                Event.at>=start,Event.at<stop).order_by(Event.at,Event.id)).all()
            result=inspect(punches,regimes.get(employee.id,"fixed"))
            for entry in result["warnings"]:
                findings.append({"employee_id":employee.id,"employee":employee.name,**entry})
        return {"year":year,"month":month,"findings":findings,
                "count":len(findings),
                "disclaimer":"Kontrolné upozornenia. Nezastupujú právne posúdenie, mzdovú uzávierku ani zohľadnenie KZ."}
