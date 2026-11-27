"""Per-terminal API credentials, idempotent RFID punch ingestion, safe offline replay.

Credentials shown once at enrollment, stored as SHA-256 digests. Replay limit
72 hours, future-clock tolerance 5 min, duplicate event UUID deduplicated.
"""
import hashlib
import secrets
from datetime import datetime,timedelta,timezone
from typing import Optional,Literal
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, Request, Header
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column, Session

TZ=ZoneInfo("Europe/Bratislava")

class DeviceCreate(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    location:str=Field(default="",max_length=160)
    allowed_ip:Optional[str]=Field(default=None,max_length=64)

class IdentifyRequest(BaseModel):
    uid:str=Field(min_length=3,max_length=128)

class KioskScan(BaseModel):
    uid:str=Field(min_length=3,max_length=128)
    event_id:str=Field(min_length=16,max_length=80)
    kind:Literal["in","out","break_start","break_end"]
    occurred_at:datetime

def _digest(token:str)->str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def install(app,Base,Employee,Event,engine,db,require_role,audit,is_closed_range):
    class TerminalDevice(Base):
        __tablename__="terminal_device"
        id:Mapped[int]=mapped_column(primary_key=True)
        name:Mapped[str]=mapped_column(String(120),unique=True)
        location:Mapped[str]=mapped_column(String(160),default="")
        secret_hash:Mapped[str]=mapped_column(String(64))
        allowed_ip:Mapped[Optional[str]]=mapped_column(String(64),nullable=True)
        active:Mapped[bool]=mapped_column(Boolean,default=True)
        last_seen:Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)
    class DeviceReceipt(Base):
        __tablename__="device_receipt"
        id:Mapped[int]=mapped_column(primary_key=True)
        device_id:Mapped[int]=mapped_column(ForeignKey("terminal_device.id"),index=True)
        event_id:Mapped[str]=mapped_column(String(80))
        event_row_id:Mapped[Optional[int]]=mapped_column(ForeignKey("event.id"),nullable=True)
        created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
        __table_args__=(UniqueConstraint("device_id","event_id",name="uq_device_event"),)
    Base.metadata.create_all(engine)
    def serialize(d):
        return {"id":d.id,"name":d.name,"location":d.location,"active":d.active,
                "allowed_ip":d.allowed_ip,"last_seen":d.last_seen}

    @app.get("/api/devices",dependencies=[Depends(require_role("admin","hr"))])
    def devices(session:Session=Depends(db)):
        return [serialize(d) for d in session.scalars(select(TerminalDevice).order_by(TerminalDevice.name)).all()]

    @app.post("/api/devices",dependencies=[Depends(require_role("admin"))])
    def create_device(data:DeviceCreate,account=Depends(require_role("admin")),session:Session=Depends(db)):
        if session.scalar(select(TerminalDevice.id).where(TerminalDevice.name==data.name)):
            raise HTTPException(409,"Zariadenie s týmto názvom už existuje")
        key=secrets.token_urlsafe(36)
        dev=TerminalDevice(name=data.name,location=data.location,
            allowed_ip=data.allowed_ip,secret_hash=_digest(key))
        session.add(dev);session.flush()
        audit(session,account.username,"device.create",str(dev.id));session.commit()
        return {**serialize(dev),"device_key":key,"warning":"Kľúč sa zobrazí iba raz. Neukladaj ho do GitHubu."}

    @app.post("/api/devices/{device_id}/rotate",dependencies=[Depends(require_role("admin"))])
    def rotate_device(device_id:int,account=Depends(require_role("admin")),session:Session=Depends(db)):
        dev=session.get(TerminalDevice,device_id)
        if not dev:raise HTTPException(404,"Terminál neexistuje")
        key=secrets.token_urlsafe(36);dev.secret_hash=_digest(key)
        audit(session,account.username,"device.rotate",str(device_id));session.commit()
        return {"device_id":device_id,"device_key":key,"warning":"Starý kľúč už neplatí; nový sa zobrazí iba raz."}

    @app.post("/api/devices/{device_id}/disable",dependencies=[Depends(require_role("admin"))])
    def disable_device(device_id:int,account=Depends(require_role("admin")),session:Session=Depends(db)):
        dev=session.get(TerminalDevice,device_id)
        if not dev:raise HTTPException(404,"Terminál neexistuje")
        dev.active=False;audit(session,account.username,"device.disable",str(device_id));session.commit()
        return {"disabled":True}

    def authenticate(request:Request, x_device_id:Optional[int]=Header(None),
                     x_device_key:Optional[str]=Header(None),session:Session=Depends(db)):
        if x_device_id is None or not x_device_key:raise HTTPException(401,"Terminál nie je autorizovaný")
        dev=session.get(TerminalDevice,x_device_id)
        if not dev or not dev.active or not secrets.compare_digest(dev.secret_hash,_digest(x_device_key)):
            raise HTTPException(401,"Neplatný terminálový kľúč")
        source_ip=request.client.host if request.client else ""
        if dev.allowed_ip and source_ip!=dev.allowed_ip:raise HTTPException(403,"Neplatná IP terminálu")
        return dev

    @app.get("/api/devices/status")
    def device_status(dev=Depends(authenticate),session:Session=Depends(db)):
        return {"device_id":dev.id,"name":dev.name,"server_utc":datetime.now(timezone.utc).isoformat()}

    @app.post("/api/devices/identify")
    def identify(payload:IdentifyRequest,dev=Depends(authenticate),session:Session=Depends(db)):
        employee=session.scalar(select(Employee).where(Employee.card_uid==payload.uid,Employee.active==True))
        if not employee:raise HTTPException(404,"Neznáma karta")
        last=session.scalar(select(Event).where(Event.employee_id==employee.id)
                .order_by(Event.at.desc(),Event.id.desc()).limit(1))
        # Last event is only an indicative presence flag.
        present=bool(last and last.kind in ("in","break_end"))
        return {"name":employee.name,"employee_id":employee.id,"present":present,
                "suggested_kind":"out" if present else "in","last_event":last.at if last else None}

    @app.post("/api/devices/punch")
    def device_punch(data:KioskScan,dev=Depends(authenticate),session:Session=Depends(db)):
        # Duplicate receipts are ACKed but never replayed into the ledger.
        existing=session.scalar(select(DeviceReceipt).where(
            DeviceReceipt.device_id==dev.id,DeviceReceipt.event_id==data.event_id))
        if existing:return {"accepted":True,"duplicate":True,"event_row_id":existing.event_row_id}
        at=data.occurred_at
        if at.tzinfo is None:raise HTTPException(422,"Udalosť musí obsahovať časové pásmo")
        at=at.astimezone(timezone.utc)
        now=datetime.now(timezone.utc)
        if at<now-timedelta(hours=72) or at>now+timedelta(minutes=5):
            raise HTTPException(422,"Offline záznam je starší než 72 h alebo čas zariadenia nesúhlasí")
        local_day=at.astimezone(TZ).date()
        if is_closed_range(session,local_day,local_day):
            raise HTTPException(409,"Mesiac dochádzky je uzavretý")
        employee=session.scalar(select(Employee).where(Employee.card_uid==data.uid,Employee.active==True))
        if not employee:raise HTTPException(404,"Neznáma RFID karta")
        # Hard dedup by time for same employee and event kind.
        nearest=session.scalar(select(Event).where(
            Event.employee_id==employee.id,Event.kind==data.kind,
            Event.at>=at-timedelta(seconds=45),Event.at<=at+timedelta(seconds=45)
        ).limit(1))
        if nearest:
            session.add(DeviceReceipt(device_id=dev.id,event_id=data.event_id,event_row_id=nearest.id))
            session.commit()
            return {"accepted":True,"duplicate":True,"event_row_id":nearest.id}
        entry=Event(employee_id=employee.id,kind=data.kind,at=at,origin="rfid",device_id=str(dev.id))
        session.add(entry);session.flush()
        session.add(DeviceReceipt(device_id=dev.id,event_id=data.event_id,event_row_id=entry.id))
        dev.last_seen=now
        audit(session,dev.name,"device.punch",str(entry.id))
        session.commit()
        return {"accepted":True,"duplicate":False,"event_row_id":entry.id,"employee":employee.name,
                "kind":data.kind,"time":at.astimezone(TZ).isoformat()}
