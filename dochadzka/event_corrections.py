"""Audited attendance punch corrections and logical voiding.

Original event rows remain in place. Action history persists old/new values and
the mandatory reason; a voided event has kind='void' and is ignored by interval
calculations. Changes in closed payroll months are prohibited.
"""
from datetime import datetime,date,timedelta,timezone
from typing import Optional,Literal
from fastapi import Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import DateTime,ForeignKey,Integer,String,select
from sqlalchemy.orm import Mapped,mapped_column,Session

class Correction(BaseModel):
    kind:Literal["in","out","break_start","break_end"]
    occurred_at:datetime
    reason:str=Field(min_length=8,max_length=400)

class VoidReason(BaseModel):
    reason:str=Field(min_length=8,max_length=400)

class ManualEvent(BaseModel):
    employee_id:int
    kind:Literal["in","out","break_start","break_end"]
    occurred_at:datetime
    reason:str=Field(min_length=8,max_length=400)

def install(app,Base,Employee,Event,engine,db,require_role,audit,is_closed_range):
    class EventRevision(Base):
        __tablename__="event_revision"
        id:Mapped[int]=mapped_column(primary_key=True)
        event_id:Mapped[int]=mapped_column(ForeignKey("event.id"),index=True)
        actor:Mapped[str]=mapped_column(String(80))
        action:Mapped[str]=mapped_column(String(30))
        before_kind:Mapped[str]=mapped_column(String(30))
        after_kind:Mapped[str]=mapped_column(String(30))
        before_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
        after_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
        reason:Mapped[str]=mapped_column(String(400))
        at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    Base.metadata.create_all(engine)
    def as_utc(value):
        if value.tzinfo is None:raise HTTPException(422,"Dátum musí obsahovať časové pásmo")
        return value.astimezone(timezone.utc)
    def not_closed(session,from_at,to_at=None):
        for stamp in (from_at,to_at):
            if stamp is None:continue
            local=stamp.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Bratislava")).date()
            if is_closed_range(session,local,local):
                raise HTTPException(409,"Záznam patrí do uzavretého mesiaca")
    def serial(e):
        return {"id":e.id,"employee_id":e.employee_id,"kind":e.kind,"at":e.at,
                "origin":e.origin,"device_id":e.device_id}
    @app.get("/api/corrections/events",dependencies=[Depends(require_role("admin","hr"))])
    def list_events(employee_id:int,start:date,end:date,session:Session=Depends(db)):
        if end<start or (end-start).days>62:raise HTTPException(422,"Maximálne 63 dní")
        if not session.get(Employee,employee_id):raise HTTPException(404,"Zamestnanec neexistuje")
        begin=datetime.combine(start,datetime.min.time,timezone.utc)-timedelta(days=1)
        finish=datetime.combine(end+timedelta(days=2),datetime.min.time,timezone.utc)
        q=select(Event).where(Event.employee_id==employee_id,Event.at>=begin,
                              Event.at<finish).order_by(Event.at,Event.id)
        return [serial(e) for e in session.scalars(q).all()]
    @app.post("/api/corrections/manual",dependencies=[Depends(require_role("admin","hr"))])
    def add_event(payload:ManualEvent,operator=Depends(require_role("admin","hr")),
                  session:Session=Depends(db)):
        if not session.get(Employee,payload.employee_id):raise HTTPException(404,"Zamestnanec neexistuje")
        at=as_utc(payload.occurred_at)
        not_closed(session,at)
        event=Event(employee_id=payload.employee_id,kind=payload.kind,at=at,
                    origin="manual",device_id=None)
        session.add(event);session.flush()
        session.add(EventRevision(event_id=event.id,actor=operator.username,action="create",
            before_kind="",after_kind=event.kind,before_at=at,after_at=at,reason=payload.reason))
        audit(session,operator.username,"event.manual",str(event.id))
        session.commit();return serial(event)
    @app.post("/api/corrections/{event_id}",dependencies=[Depends(require_role("admin","hr"))])
    def correct(event_id:int,payload:Correction,operator=Depends(require_role("admin","hr")),
                session:Session=Depends(db)):
        event=session.get(Event,event_id)
        if not event:raise HTTPException(404,"Udalosť neexistuje")
        if event.kind=="void":raise HTTPException(409,"Zneplatnený záznam nemožno opravovať")
        new_at=as_utc(payload.occurred_at)
        old_at=event.at.replace(tzinfo=timezone.utc) if event.at.tzinfo is None else event.at
        not_closed(session,old_at,new_at)
        before_kind=event.kind
        event.kind=payload.kind;event.at=new_at;event.origin="manual"
        session.add(EventRevision(event_id=event.id,actor=operator.username,action="correct",
            before_kind=before_kind,after_kind=event.kind,before_at=old_at,
            after_at=new_at,reason=payload.reason))
        audit(session,operator.username,"event.correct",str(event.id))
        session.commit();return serial(event)
    @app.post("/api/corrections/{event_id}/void",dependencies=[Depends(require_role("admin","hr"))])
    def void(event_id:int,payload:VoidReason,operator=Depends(require_role("admin","hr")),
             session:Session=Depends(db)):
        event=session.get(Event,event_id)
        if not event:raise HTTPException(404,"Udalosť neexistuje")
        if event.kind=="void":raise HTTPException(409,"Záznam už je zneplatnený")
        old_at=event.at.replace(tzinfo=timezone.utc) if event.at.tzinfo is None else event.at
        not_closed(session,old_at)
        old_kind=event.kind
        event.kind="void";event.origin="manual"
        session.add(EventRevision(event_id=event.id,actor=operator.username,action="void",
            before_kind=old_kind,after_kind="void",before_at=old_at,after_at=old_at,
            reason=payload.reason))
        audit(session,operator.username,"event.void",str(event.id))
        session.commit();return serial(event)
    @app.get("/api/corrections/history/{event_id}",dependencies=[Depends(require_role("admin","hr"))])
    def history(event_id:int,session:Session=Depends(db)):
        rows=session.scalars(select(EventRevision).where(EventRevision.event_id==event_id)
            .order_by(EventRevision.id)).all()
        return [{"action":r.action,"actor":r.actor,"reason":r.reason,
                 "before_kind":r.before_kind,"after_kind":r.after_kind,
                 "before_at":r.before_at,"after_at":r.after_at,"at":r.at} for r in rows]
