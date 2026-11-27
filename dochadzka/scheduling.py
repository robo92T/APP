"""Shift scheduling and indicative time balance."""
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Date, ForeignKey, Integer, String, select, text
from sqlalchemy.orm import Mapped, mapped_column, Session
from legal_calendar import is_workday
TZ=ZoneInfo("Europe/Bratislava")
class ShiftIn(BaseModel):
    employee_id:int
    day:date
    planned_minutes:int=Field(ge=0,le=1440)
    start_time:str="08:00"
    end_time:str="16:00"
    note:str=Field(default="",max_length=200)
def install(app,Base,Employee,Event,Absence,engine,db,admin,audit):
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
    @app.get("/api/shifts",dependencies=[Depends(admin)])
    def shifts(start:date,end:date,employee_id:Optional[int]=None,session:Session=Depends(db)):
        q=select(Shift).where(Shift.day>=start,Shift.day<=end)
        if employee_id:q=q.where(Shift.employee_id==employee_id)
        return [{"id":x.id,"employee_id":x.employee_id,"day":x.day,"planned_minutes":x.planned_minutes,"start_time":x.start_time,"end_time":x.end_time,"note":x.note} for x in session.scalars(q).all()]
    @app.post("/api/shifts",dependencies=[Depends(admin)])
    def save_shift(p:ShiftIn,session:Session=Depends(db)):
        if not session.get(Employee,p.employee_id):raise HTTPException(404,"Zamestnanec neexistuje")
        if session.execute(text("SELECT 1 FROM month_close WHERE year=:year AND month=:month"),{"year":p.day.year,"month":p.day.month}).first():raise HTTPException(409,"Mesiac je uzavretý")
        try:
            datetime.strptime(p.start_time,"%H:%M");datetime.strptime(p.end_time,"%H:%M")
        except ValueError:raise HTTPException(422,"Neplatný čas")
        s=session.scalar(select(Shift).where(Shift.employee_id==p.employee_id,Shift.day==p.day))
        if not s:
            s=Shift(employee_id=p.employee_id,day=p.day);session.add(s)
        s.planned_minutes=p.planned_minutes;s.start_time=p.start_time;s.end_time=p.end_time;s.note=p.note
        audit(session,"admin","shift.save",f"{p.employee_id}/{p.day}");session.commit()
        return {"success":True}
    @app.get("/api/saldo/{employee_id}",dependencies=[Depends(admin)])
    def saldo(employee_id:int,start:date,end:date,session:Session=Depends(db)):
        e=session.get(Employee,employee_id)
        if not e:raise HTTPException(404,"Zamestnanec neexistuje")
        if end<start or (end-start).days>366:raise HTTPException(422,"Neplatné obdobie")
        shift_map={s.day:s for s in session.scalars(select(Shift).where(Shift.employee_id==employee_id,Shift.day>=start,Shift.day<=end)).all()}
        absences=session.scalars(select(Absence).where(Absence.employee_id==employee_id,Absence.status=="approved",Absence.start<=end,Absence.end>=start)).all()
        begin=datetime.combine(start,time.min,TZ).astimezone(timezone.utc)
        finish=datetime.combine(end+timedelta(days=1),time.min,TZ).astimezone(timezone.utc)
        events=session.scalars(select(Event).where(Event.employee_id==employee_id,Event.at>=begin,Event.at<finish).order_by(Event.at,Event.id)).all()
        day_events={}
        for ev in events:
            at=ev.at.replace(tzinfo=timezone.utc) if ev.at.tzinfo is None else ev.at
            day_events.setdefault(at.astimezone(TZ).date(),[]).append((ev.kind,at))
        records=[];d=start
        credited_kinds={"vacation","doctor","accompany","paid_leave","wedding","funeral","blood_donation","training","business_trip"}
        while d<=end:
            shift=shift_map.get(d)
            plan=shift.planned_minutes if shift else (e.weekly_minutes//e.work_days if is_workday(d) and d.weekday()<e.work_days else 0)
            absence_types=[];credited=0
            for a in absences:
                if a.start<=d<=a.end:
                    absence_types.append(a.kind)
                    if a.kind in credited_kinds:credited+=a.minutes if a.minutes is not None and a.start==a.end else plan
            credited=min(credited,plan)
            started=None;pause=None;pause_minutes=0;worked=0;warnings=[]
            for kind,at in day_events.get(d,[]):
                if kind=="in":
                    if started is not None:warnings.append("duplicitný príchod")
                    else:started=at;pause=None;pause_minutes=0
                elif kind=="break_start":
                    if started is not None and pause is None:pause=at
                    else:warnings.append("neplatná prestávka")
                elif kind=="break_end":
                    if pause is not None:pause_minutes+=max(0,int((at-pause).total_seconds()//60));pause=None
                    else:warnings.append("neplatný koniec prestávky")
                elif kind=="out":
                    if started is None:warnings.append("odchod bez príchodu")
                    else:
                        if pause is not None:pause_minutes+=max(0,int((at-pause).total_seconds()//60))
                        worked+=max(0,int((at-started).total_seconds()//60)-pause_minutes)
                        started=None;pause=None;pause_minutes=0
            if started is not None:warnings.append("neukončená smena")
            if worked>0 and credited>0:warnings.append("práca a platené voľno v jeden deň – preveriť prekryv")
            records.append({"date":d.isoformat(),"planned_minutes":plan,"worked_minutes":worked,"credited_minutes":credited,"saldo_minutes":worked+credited-plan,"absences":absence_types,"warnings":warnings})
            d+=timedelta(days=1)
        totals={k:sum(r[k] for r in records) for k in ("planned_minutes","worked_minutes","credited_minutes","saldo_minutes")}
        return {"employee_id":employee_id,"from":start,"to":end,"totals":totals,"rows":records,"warning":"Len informatívne saldo. Pri cezpolnočných zmenách, nerovnomernom rozvrhu, sviatkoch, platených absenciách a nadčasoch treba samostatné odborné overenie."}
    return Shift
