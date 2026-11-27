"""Self-service employee APIs. Never let a user choose another employee_id."""
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

class SelfAbsence(BaseModel):
    kind: str
    start: date
    end: date
    minutes: int | None = Field(default=None,ge=1,le=1440)
    note: str = Field(default="",max_length=400)

ALLOWED={"vacation","doctor","accompany","doctor_unpaid","accompany_unpaid","unpaid","paid_leave","ocr","other"}
def install(app,Employee,Event,Absence,db,current_account,audit):
    def mine(account=Depends(current_account),session:Session=Depends(db)):
        if account.employee_id is None:raise HTTPException(403,"Účet nie je priradený zamestnancovi")
        employee=session.get(Employee,account.employee_id)
        if employee is None or not employee.active:raise HTTPException(403,"Neaktívny zamestnanec")
        return employee
    @app.get("/api/me/summary")
    def summary(employee=Depends(mine),session:Session=Depends(db)):
        tz=ZoneInfo("Europe/Bratislava")
        now=datetime.now(tz);first=date(now.year,now.month,1)
        nxt=date(now.year+(1 if now.month==12 else 0),1 if now.month==12 else now.month+1,1)
        start=datetime.combine(first,time.min,tz).astimezone(timezone.utc)
        stop=datetime.combine(nxt,time.min,tz).astimezone(timezone.utc)
        events=session.scalars(select(Event).where(Event.employee_id==employee.id,Event.at>=start,Event.at<stop).order_by(Event.at,Event.id)).all()
        opening=None;pause=None;pauses=0;worked=0;warnings=[];last=None
        for e in events:
            at=e.at.replace(tzinfo=timezone.utc) if e.at.tzinfo is None else e.at
            last={"kind":e.kind,"at":at.astimezone(tz).isoformat()}
            if e.kind=="in":
                if opening is not None:warnings.append("duplicitný príchod")
                else:opening=at;pause=None;pauses=0
            elif e.kind=="break_start":
                if opening is not None and pause is None:pause=at
            elif e.kind=="break_end":
                if pause is not None:pauses+=max(0,int((at-pause).total_seconds()//60));pause=None
            elif e.kind=="out":
                if opening is None:warnings.append("odchod bez príchodu")
                else:
                    if pause is not None:pauses+=max(0,int((at-pause).total_seconds()//60))
                    worked+=max(0,int((at-opening).total_seconds()//60)-pauses)
                    opening=None;pause=None;pauses=0
        if opening is not None:warnings.append("neukončená smena")
        absences=session.scalars(select(Absence).where(Absence.employee_id==employee.id,Absence.start<nxt,Absence.end>=first)).all()
        requests=[{"id":a.id,"kind":a.kind,"start":a.start.isoformat(),"end":a.end.isoformat(),"status":a.status,"minutes":a.minutes} for a in absences]
        return {"name":employee.name,"period":first.strftime("%Y-%m"),"weekly_minutes":employee.weekly_minutes,"worked_minutes":worked,"last_event":last,"warnings":warnings,"requests":requests,"note":"Odpracované minúty sú orientačné; otvorené zmeny nie sú započítané."}
    @app.post("/api/me/absences",status_code=201)
    def create_absence(data:SelfAbsence,account=Depends(current_account),employee=Depends(mine),session:Session=Depends(db)):
        if data.kind not in ALLOWED:raise HTTPException(422,"Neplatný druh žiadosti")
        if data.end<data.start or (data.end-data.start).days>366:raise HTTPException(422,"Neplatné obdobie")
        # No client-controlled employee ID: derive identity from verified token.
        item=Absence(employee_id=employee.id,kind=data.kind,start=data.start,end=data.end,minutes=data.minutes,status="pending",note=data.note)
        session.add(item);session.flush()
        audit(session,account.username,"self.absence.create",str(item.id));session.commit()
        return {"id":item.id,"status":"pending"}
