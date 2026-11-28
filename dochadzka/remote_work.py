"""Self-service home-office attendance: authenticated, consent-based and privacy-minimising.

GPS is optional and is never persisted. Location is only checked for plausibility,
not proof of physical presence. No tracking, geofence or stored home address.
A remote punch requires an HR-approved home-office day.
"""
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional, Literal
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

TZ=ZoneInfo("Europe/Bratislava")
class RemotePunch(BaseModel):
    kind:Literal["in","out","break_start","break_end"]
    # Optional one-shot GPS evidence, discarded after request validation.
    gps_lat:Optional[float]=Field(default=None,ge=-90,le=90)
    gps_lon:Optional[float]=Field(default=None,ge=-180,le=180)
    gps_accuracy_m:Optional[float]=Field(default=None,ge=0,le=100000)
    gps_permission_confirmed:bool=False

def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def install(app,Employee,Event,Absence,db,current_account,audit,is_closed_range):
    def who(account=Depends(current_account),session:Session=Depends(db)):
        if not account.employee_id:raise HTTPException(403,"Účet nie je priradený zamestnancovi")
        e=session.get(Employee,account.employee_id)
        if not e or not e.active:raise HTTPException(403,"Neaktívny zamestnanec")
        return e
    def eligible(session,employee,today):
        return bool(session.scalar(select(Absence.id).where(
            Absence.employee_id==employee.id,Absence.kind=="home_office",
            Absence.status=="approved",Absence.start<=today,Absence.end>=today).limit(1)))
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
    @app.get("/api/me/remote-status")
    def status(employee=Depends(who),session:Session=Depends(db)):
        now=datetime.now(timezone.utc);today=now.astimezone(TZ).date()
        valid=eligible(session,employee,today)
        latest=recent_events(session,employee,now)
        # This is not a GPS or continuous monitoring service.
        return {"today":today.isoformat(),"approved_home_office":valid,
            "state":state(latest),"remote_punch_enabled":valid and not is_closed_range(session,today,today),
            "last_event":({"kind":latest[-1].kind,"at":utc(latest[-1].at).isoformat(),
                           "origin":latest[-1].origin} if latest else None),
            "gps_tracking":False,
            "note":"Pípačka vyžaduje schválený home office. GPS sa neukladá, poloha nie je podmienkou ani dôkazom výkonu práce."}
    @app.post("/api/me/remote-punch",status_code=201)
    def punch(payload:RemotePunch,employee=Depends(who),account=Depends(current_account),
              session:Session=Depends(db)):
        now=datetime.now(timezone.utc)
        today=now.astimezone(TZ).date()
        if not eligible(session,employee,today):raise HTTPException(403,"Dnes nemáš schválený home office")
        if is_closed_range(session,today,today):raise HTTPException(409,"Mesiac je uzavretý")
        submitted=(payload.gps_lat is not None,payload.gps_lon is not None,payload.gps_accuracy_m is not None)
        if any(submitted) and not all(submitted):
            raise HTTPException(422,"Pre GPS zadaj kompletný jednorazový údaj")
        if any(submitted) and not payload.gps_permission_confirmed:
            raise HTTPException(422,"Vyžaduje sa potvrdenie jednorazového povolenia polohy")
        recent=recent_events(session,employee,now)
        # Do not allow rapid duplicate punch; no client-supplied timestamp or ID.
        if recent and (now-utc(recent[-1].at)).total_seconds()<60:
            raise HTTPException(429,"Pred ďalším pípnutím počkaj aspoň 60 sekúnd")
        status=state(recent)
        allowed={"off":{"in"},"working":{"out","break_start"},"break":{"break_end"}}
        if payload.kind not in allowed[status]:
            raise HTTPException(409,"Neplatná postupnosť pípnutí pre aktuálny stav")
        entry=Event(employee_id=employee.id,kind=payload.kind,at=now,
                    origin="home_office_web",device_id=None)
        session.add(entry);session.flush()
        # Explicitly avoid storing location, even in audit logs.
        audit(session,account.username,"home_office.punch",
              f"employee={employee.id};event={entry.id};kind={payload.kind};gps_optional={all(submitted)}")
        session.commit()
        return {"id":entry.id,"kind":entry.kind,"at":now.isoformat(),
                "state":state([*recent,entry]),"gps_saved":False,
                "message":"Pípnutie zaznamenané zo serverového času; GPS súradnice neboli uložené."}
