"""Separate full-day approved home office from permission-gated field GPS punches.

Home office never asks for geolocation or requires employee punch events:
its 8h administrative work credit is derived by pdf_reports.build_rows.
Mobile field punches require an explicit administrator grant AND one-shot GPS.
The GPS coordinates are used only to validate the request and are never saved.
"""
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Literal
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, Mapped, mapped_column
from sqlalchemy import Boolean, ForeignKey, String, DateTime

TZ=ZoneInfo("Europe/Bratislava")

class RemotePunch(BaseModel):
    kind:Literal["in","out","break_start","break_end"]
    gps_lat:Optional[float]=Field(default=None,ge=-90,le=90)
    gps_lon:Optional[float]=Field(default=None,ge=-180,le=180)
    gps_accuracy_m:Optional[float]=Field(default=None,ge=0,le=100000)
    gps_permission_confirmed:bool=False

class FieldPunchToggle(BaseModel):
    enabled:bool

def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def install(app,Base,engine,Employee,Event,Absence,db,current_account,require_role,audit,is_closed_range):
    class FieldPunchPermission(Base):
        __tablename__="field_punch_permission"
        employee_id:Mapped[int]=mapped_column(ForeignKey("employee.id"),primary_key=True)
        enabled:Mapped[bool]=mapped_column(Boolean,default=False,nullable=False)
        updated_by:Mapped[str]=mapped_column(String(80),default="")
        updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
    Base.metadata.create_all(engine)

    def who(account=Depends(current_account),session:Session=Depends(db)):
        if not account.employee_id:raise HTTPException(403,"Účet nie je priradený zamestnancovi")
        e=session.get(Employee,account.employee_id)
        if not e or not e.active:raise HTTPException(403,"Neaktívny zamestnanec")
        return e

    def approved_home_office(session,employee,on_day):
        return bool(session.scalar(select(Absence.id).where(
            Absence.employee_id==employee.id,Absence.kind=="home_office",
            Absence.status=="approved",Absence.start<=on_day,Absence.end>=on_day).limit(1)))

    def granted(session,employee):
        permission=session.get(FieldPunchPermission,employee.id)
        return bool(permission and permission.enabled)

    def recent_events(session,employee,now):
        begin=now-timedelta(hours=36)
        return session.scalars(select(Event).where(
            Event.employee_id==employee.id,Event.at>=begin,
            Event.at<=now).order_by(Event.at,Event.id)).all()

    def state(events):
        open_work=False;on_break=False
        for e in events:
            if e.kind=="void":continue
            if e.kind=="in":open_work=True;on_break=False
            elif e.kind=="out":open_work=False;on_break=False
            elif e.kind=="break_start" and open_work:on_break=True
            elif e.kind=="break_end" and open_work:on_break=False
        return ("break" if on_break else "working" if open_work else "off")

    @app.get("/api/admin/field-punch-permissions")
    def list_permissions(_actor=Depends(require_role("admin")),session:Session=Depends(db)):
        employees=session.scalars(select(Employee).order_by(Employee.name)).all()
        enabled_ids=set(session.scalars(select(FieldPunchPermission.employee_id).where(
            FieldPunchPermission.enabled==True)).all())
        return [{"employee_id":p.id,"name":p.name,"active":p.active,
                 "enabled":p.id in enabled_ids} for p in employees]

    @app.patch("/api/admin/field-punch-permissions/{employee_id}")
    def change_permission(employee_id:int,payload:FieldPunchToggle,
                          actor=Depends(require_role("admin")),session:Session=Depends(db)):
        employee=session.get(Employee,employee_id)
        if not employee:raise HTTPException(404,"Zamestnanec neexistuje")
        if payload.enabled and not employee.active:
            raise HTTPException(409,"Neaktívnemu zamestnancovi nemožno povoliť terénne pípnutie")
        item=session.get(FieldPunchPermission,employee_id)
        if not item:
            item=FieldPunchPermission(employee_id=employee_id)
            session.add(item)
        item.enabled=payload.enabled
        item.updated_by=actor.username
        item.updated_at=datetime.now(timezone.utc)
        audit(session,actor.username,"field_punch.permission",
              f"employee={employee_id};enabled={payload.enabled}")
        session.commit()
        return {"employee_id":employee_id,"enabled":item.enabled}

    @app.get("/api/me/remote-status")
    def status(employee=Depends(who),session:Session=Depends(db)):
        now=datetime.now(timezone.utc);today=now.astimezone(TZ).date()
        home=approved_home_office(session,employee,today)
        field=granted(session,employee)
        events=recent_events(session,employee,now)
        permitted=field and not home and not is_closed_range(session,today,today)
        return {"today":today.isoformat(),
            "approved_home_office":home,
            "home_office_no_punch_required":home,
            "field_punch_enabled":field,
            "remote_punch_enabled":permitted,
            "state":state(events),
            "last_event":({"kind":events[-1].kind,"at":utc(events[-1].at).isoformat(),
                           "origin":events[-1].origin} if events else None),
            "gps_tracking":False,"gps_saved":False,
            "note":("Schválený home office sa automaticky počíta ako 8 hodín bez GPS a pípnutia."
                    if home else "Terénne GPS pípnutie je dostupné len po povolení administrátorom. "
                    "Súradnice sa neukladajú.")}

    @app.post("/api/me/remote-punch",status_code=201)
    def punch(payload:RemotePunch,employee=Depends(who),account=Depends(current_account),
              session:Session=Depends(db)):
        now=datetime.now(timezone.utc);today=now.astimezone(TZ).date()
        if approved_home_office(session,employee,today):
            raise HTTPException(403,"Pri schválenom home office sa 8 hodín započítava automaticky. Nepípaj.")
        if not granted(session,employee):
            raise HTTPException(403,"GPS pípnutie v teréne musí najprv povoliť administrátor")
        if is_closed_range(session,today,today):
            raise HTTPException(409,"Mesiac je uzavretý")
        submitted=(payload.gps_lat is not None,payload.gps_lon is not None,
                   payload.gps_accuracy_m is not None)
        if not all(submitted) or not payload.gps_permission_confirmed:
            raise HTTPException(422,"Pri terénnom pípnutí potvrď jednorazové GPS a odošli úplnú polohu")
        recent=recent_events(session,employee,now)
        if recent and (now-utc(recent[-1].at)).total_seconds()<60:
            raise HTTPException(429,"Pred ďalším pípnutím počkaj aspoň 60 sekúnd")
        current=state(recent)
        allowed={"off":{"in"},"working":{"out","break_start"},"break":{"break_end"}}
        if payload.kind not in allowed[current]:
            raise HTTPException(409,"Neplatná postupnosť pípnutí pre aktuálny stav")
        entry=Event(employee_id=employee.id,kind=payload.kind,at=now,
                    origin="field_gps",device_id=None)
        session.add(entry);session.flush()
        # Coordinates are deliberately never written to any table, logs or audit.
        audit(session,account.username,"field_punch.record",
              f"employee={employee.id};event={entry.id};kind={payload.kind};gps_one_shot=True")
        session.commit()
        return {"id":entry.id,"kind":entry.kind,"at":now.isoformat(),
                "state":state([*recent,entry]),"gps_saved":False,
                "message":"Terénne pípnutie zaznamenané podľa serverového času; poloha sa neukladá."}
