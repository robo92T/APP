"""Shift scheduling and indicative time balance."""
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Date, ForeignKey, Integer, String, select, text
from sqlalchemy.orm import Mapped, mapped_column, Session
from legal_calendar import is_workday
from work_rules import SHIFT_PRESETS,schedule_span_minutes
TZ=ZoneInfo("Europe/Bratislava")
class ShiftIn(BaseModel):
    employee_id:int
    day:date
    planned_minutes:int=Field(ge=0,le=1440)
    start_time:str="08:00"
    end_time:str="16:00"
    note:str=Field(default="",max_length=200)
    preset:Optional[str]=None
class CycleIn(BaseModel):
    employee_id:int
    start:date
    end:date
    cycle:str=Field(default="D-N-V-V",max_length=64)
    offset:int=Field(default=0,ge=0,le=365)
    overwrite:bool=False
    day_minutes:int=Field(default=660,ge=0,le=1440)
    night_minutes:int=Field(default=660,ge=0,le=1440)

def install(app,Base,Employee,Event,Absence,engine,db,admin,audit,require_role):
    class Shift(Base):
        __tablename__="shift"
        id:Mapped[int]=mapped_column(primary_key=True)
        employee_id:Mapped[int]=mapped_column(ForeignKey("employee.id"),index=True)
        day:Mapped[date]=mapped_column(Date,index=True)
        planned_minutes:Mapped[int]=mapped_column(Integer)
        start_time:Mapped[str]=mapped_column(String(5))
        end_time:Mapped[str]=mapped_column(String(5))
        note:Mapped[str]=mapped_column(String(200),default="")
    Base.metadata.create_all(engine)
    @app.get("/api/shift-presets",dependencies=[Depends(require_role("admin","hr","scheduler"))])
    def shift_presets():return SHIFT_PRESETS
    @app.get("/api/scheduler/employees",dependencies=[Depends(require_role("admin","hr","scheduler"))])
    def scheduler_employees(session:Session=Depends(db)):
        return [{"id":x.id,"name":x.name} for x in session.scalars(select(Employee).where(Employee.active==True).order_by(Employee.name)).all()]
    @app.get("/api/shifts",dependencies=[Depends(require_role("admin","hr","scheduler"))])
    def shifts(start:date,end:date,employee_id:Optional[int]=None,session:Session=Depends(db)):
        q=select(Shift).where(Shift.day>=start,Shift.day<=end)
        if employee_id:q=q.where(Shift.employee_id==employee_id)
        return [{"id":x.id,"employee_id":x.employee_id,"day":x.day,"planned_minutes":x.planned_minutes,"start_time":x.start_time,"end_time":x.end_time,"note":x.note} for x in session.scalars(q).all()]
    @app.post("/api/shifts",dependencies=[Depends(require_role("admin","hr","scheduler"))])
    def save_shift(p:ShiftIn,actor=Depends(require_role("admin","hr","scheduler")),session:Session=Depends(db)):
        if not session.get(Employee,p.employee_id):raise HTTPException(404,"Zamestnanec neexistuje")
        if session.execute(text("SELECT 1 FROM month_close WHERE year=:year AND month=:month"),{"year":p.day.year,"month":p.day.month}).first():raise HTTPException(409,"Mesiac je uzavretý")
        if p.preset:
            if p.preset not in SHIFT_PRESETS:raise HTTPException(422,"Neznáma šablóna zmeny")
            preset=SHIFT_PRESETS[p.preset]
            p.start_time=preset["start_time"]
            p.end_time=preset["end_time"]
            p.planned_minutes=preset["planned_minutes"]
        try:
            datetime.strptime(p.start_time,"%H:%M");datetime.strptime(p.end_time,"%H:%M")
        except ValueError:raise HTTPException(422,"Neplatný čas")
        gross=schedule_span_minutes(p.start_time,p.end_time)
        if p.planned_minutes>gross and p.planned_minutes>0:
            raise HTTPException(422,"Čistý plánovaný čas nemôže byť dlhší ako čas medzi začiatkom a koncom zmeny")
        if gross>360 and gross-p.planned_minutes<30:
            raise HTTPException(422,"Pri zmene dlhšej ako 6 hodín zohľadni aspoň 30-minútovú prestávku alebo osobitnú zákonnú výnimku")
        s=session.scalar(select(Shift).where(Shift.employee_id==p.employee_id,Shift.day==p.day))
        if not s:
            s=Shift(employee_id=p.employee_id,day=p.day);session.add(s)
        s.planned_minutes=p.planned_minutes;s.start_time=p.start_time;s.end_time=p.end_time;s.note=p.note
        audit(session,actor.username,"shift.save",f"{p.employee_id}/{p.day}");session.commit()
        return {"success":True}
    @app.post("/api/shifts/generate-cycle",dependencies=[Depends(require_role("admin","hr","scheduler"))])
    def generate_cycle(p:CycleIn,actor=Depends(require_role("admin","hr","scheduler")),session:Session=Depends(db)):
        """D-N-V-V 24/7 sequence. Values are HR-confirmed planned minutes, not law-derived."""
        if not session.get(Employee,p.employee_id):raise HTTPException(404,"Zamestnanec neexistuje")
        if p.end<p.start or (p.end-p.start).days>366:raise HTTPException(422,"Rozsah je maximálne 367 dní")
        kinds=[x.strip().upper() for x in p.cycle.split("-")]
        if not kinds or any(x not in ("D","N","V","R","P","H") for x in kinds):raise HTTPException(422,"Cyklus povoľuje D, N, R, P, H, V")
        day=p.start
        created=0;skipped=0
        while day<=p.end:
            if session.execute(text("SELECT 1 FROM month_close WHERE year=:year AND month=:month"),{"year":day.year,"month":day.month}).first():
                raise HTTPException(409,f"Uzavretý mesiac {day.year}-{day.month:02d}")
            day+=timedelta(days=1)
        day=p.start
        while day<=p.end:
            kind=kinds[((day-p.start).days+p.offset)%len(kinds)]
            rule={"D":("06:00","18:00",p.day_minutes),"N":("18:00","06:00",p.night_minutes),"R":("06:00","12:00",360),"P":("12:00","18:00",360),"H":("06:00","12:00",360),"V":("00:00","00:00",0)}[kind]
            existing=session.scalar(select(Shift).where(Shift.employee_id==p.employee_id,Shift.day==day))
            if existing and not p.overwrite:skipped+=1
            else:
                record=existing or Shift(employee_id=p.employee_id,day=day)
                record.start_time=rule[0];record.end_time=rule[1];record.planned_minutes=rule[2]
                record.note=f"Cyklus {p.cycle} · {kind}; plánované minúty potvrďte personalistom"
                if not existing:session.add(record)
                created+=1
            day+=timedelta(days=1)
        audit(session,actor.username,"shifts.cycle.generate",f"{p.employee_id}:{p.start}/{p.end}:{created}")
        session.commit()
        return {"created_or_updated":created,"skipped":skipped,"warning":"Zmeny nad 12 h, prestávky a minimálne odpočinky vyžadujú samostatnú kontrolu."}
    @app.get("/api/saldo/{employee_id}",dependencies=[Depends(admin)])
    def saldo(employee_id:int,start:date,end:date,session:Session=Depends(db)):
        e=session.get(Employee,employee_id)
        if not e:raise HTTPException(404,"Zamestnanec neexistuje")
        if end<start or (end-start).days>366:raise HTTPException(422,"Neplatné obdobie")
        from pdf_reports import build_rows
        # Same midnight-safe calculation used by monthly PDFs.
        from_utc=datetime.combine(start-timedelta(days=2),time.min,TZ).astimezone(timezone.utc)
        to_utc=datetime.combine(end+timedelta(days=2),time.min,TZ).astimezone(timezone.utc)
        events=session.scalars(select(Event).where(
            Event.employee_id==employee_id,Event.at>=from_utc,Event.at<to_utc
        ).order_by(Event.at,Event.id)).all()
        all_shifts=session.scalars(select(Shift).where(
            Shift.employee_id==employee_id,Shift.day>=start-timedelta(days=1),
            Shift.day<=end)).all()
        shift_map={r.day:r for r in all_shifts}
        absences=session.scalars(select(Absence).where(
            Absence.employee_id==employee_id,Absence.status=="approved",
            Absence.start<=end,Absence.end>=start)).all()
        profile=Base.metadata.tables.get("employee_profile")
        if profile is not None:
            regime=session.execute(select(profile.c.work_regime).where(
                profile.c.employee_id==employee_id)).scalar_one_or_none()
            if regime:e.work_regime=regime
        rows=[]
        cursor=date(start.year,start.month,1)
        while cursor<=end:
            for r in build_rows(e,events,shift_map,absences,cursor.year,cursor.month):
                if not start<=r["day"]<=end:continue
                rows.append({"date":r["day"].isoformat(),"planned_minutes":r["plan"],
                    "worked_minutes":r["worked"],"credited_minutes":r["credit"],
                    "saldo_minutes":r["saldo"],"break_minutes":r["breaks"],
                    "absences":r["absence"].split(", ") if r["absence"] else [],
                    "warnings":r["warnings"]})
            cursor=date(cursor.year+1,1,1) if cursor.month==12 else date(cursor.year,cursor.month+1,1)
        totals={key:sum(r[key] for r in rows) for key in
            ("planned_minutes","worked_minutes","credited_minutes","saldo_minutes","break_minutes")}
        return {"employee_id":employee_id,"from":start,"to":end,"totals":totals,
            "rows":rows,"warning":"Saldo je informatívne a používa automatický obed, ak nie je skutočne odpípaný; mzdové klasifikácie zo samostatnej agendy musí HR zosúladiť pred exportom."}

    return Shift
