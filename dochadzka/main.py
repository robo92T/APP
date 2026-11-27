"""SK Dochadzka: modular attendance MVP; not a certified payroll engine."""
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo
import holidays
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, DateTime, Date, ForeignKey, Boolean, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./attendance.db")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)
TZ = ZoneInfo("Europe/Bratislava")
app = FastAPI(title="SK Dochádzka", version="0.1.0", description="API pre dochádzku, absencie, schvaľovanie a Raspberry Pi RFID")
class Base(DeclarativeBase): pass
class Employee(Base):
    __tablename__ = "employee"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    card_uid: Mapped[Optional[str]] = mapped_column(String(128), unique=True)
    weekly_minutes: Mapped[int] = mapped_column(Integer, default=2400)
    work_days: Mapped[int] = mapped_column(Integer, default=5)
    annual_leave_weeks: Mapped[int] = mapped_column(Integer, default=4)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
class Event(Base):
    __tablename__ = "event"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    origin: Mapped[str] = mapped_column(String(30), default="web")
    device_id: Mapped[Optional[str]] = mapped_column(String(80))
class Absence(Base):
    __tablename__ = "absence"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    minutes: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    note: Mapped[str] = mapped_column(String(400), default="")
class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str] = mapped_column(String(500))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
Base.metadata.create_all(engine)
def db():
    with SessionLocal() as session: yield session
def admin(x_admin_key: Optional[str] = Header(None)):
    key = os.getenv("ADMIN_API_KEY")
    if not key or not secrets.compare_digest(x_admin_key or "", key):
        raise HTTPException(401, "Neplatný administrátorský kľúč")
def terminal(x_terminal_key: Optional[str] = Header(None)):
    key = os.getenv("TERMINAL_API_KEY")
    if not key or not secrets.compare_digest(x_terminal_key or "", key):
        raise HTTPException(401, "Neplatný kľúč terminálu")
def audit(db: Session, actor: str, action: str, detail: str):
    db.add(Audit(actor=actor,action=action,detail=detail))
class EmployeeCreate(BaseModel):
    name: str = Field(min_length=2,max_length=160)
    card_uid: Optional[str] = None
    weekly_minutes: int = Field(default=2400,ge=60,le=3600)
    work_days: int = Field(default=5,ge=1,le=7)
    annual_leave_weeks: int = Field(default=4,ge=4,le=10)
    start_date: date
class PunchRequest(BaseModel):
    card_uid: str
    device_id: str = "rpi-01"
    kind: str = "toggle"
class AbsenceCreate(BaseModel):
    employee_id: int
    kind: str
    start: date
    end: date
    minutes: Optional[int] = Field(default=None,ge=1,le=1440)
    note: str = Field(default="",max_length=400)
KINDS = {"vacation","doctor","accompany","doctor_unpaid","accompany_unpaid","sick","ocr","maternity","paternity","parental","unpaid","paid_leave","business_trip","training","wedding","funeral","blood_donation","other"}
@app.get("/health")
def health(): return {"status":"ok"}
@app.get("/api/employees", dependencies=[Depends(admin)])
def employees(db: Session = Depends(db)):
    return [{"id":e.id,"name":e.name,"weekly_minutes":e.weekly_minutes,"work_days":e.work_days,"annual_leave_weeks":e.annual_leave_weeks,"start_date":e.start_date,"active":e.active} for e in db.scalars(select(Employee)).all()]
@app.post("/api/employees", dependencies=[Depends(admin)])
def add_employee(data: EmployeeCreate, db: Session = Depends(db)):
    if data.card_uid and db.scalar(select(Employee).where(Employee.card_uid==data.card_uid)): raise HTTPException(409,"Karta už existuje")
    e = Employee(**data.model_dump()); db.add(e); db.flush()
    audit(db,"admin","employee.create",str(e.id)); db.commit()
    return {"id":e.id}
@app.post("/api/terminal/punch", dependencies=[Depends(terminal)])
def punch(data: PunchRequest, db: Session = Depends(db)):
    e = db.scalar(select(Employee).where(Employee.card_uid==data.card_uid,Employee.active==True))
    if not e: raise HTTPException(404,"Neznáma alebo neaktívna karta")
    last = db.scalar(select(Event).where(Event.employee_id==e.id).order_by(Event.at.desc(),Event.id.desc()).limit(1))
    now = datetime.now(timezone.utc)
    if last and (now-last.at.replace(tzinfo=timezone.utc) if last.at.tzinfo is None else now-last.at).total_seconds()<10:
        raise HTTPException(429,"Opakované načítanie karty")
    kind = data.kind
    if kind=="toggle": kind = "out" if last and last.kind in ("in","break_end") else "in"
    if kind not in {"in","out","break_start","break_end"}: raise HTTPException(400,"Neplatná udalosť")
    ev = Event(employee_id=e.id,kind=kind,at=now,origin="rfid",device_id=data.device_id)
    db.add(ev);audit(db,data.device_id,"punch",f"{e.id}:{kind}");db.commit()
    return {"employee":e.name,"kind":kind,"time":now.astimezone(TZ).isoformat()}
@app.post("/api/absences", dependencies=[Depends(admin)])
def add_absence(data: AbsenceCreate, db: Session = Depends(db)):
    if data.kind not in KINDS: raise HTTPException(400,"Neznámy druh neprítomnosti")
    if data.end < data.start: raise HTTPException(400,"Koniec pred začiatkom")
    if not db.get(Employee,data.employee_id): raise HTTPException(404,"Zamestnanec neexistuje")
    a=Absence(**data.model_dump());db.add(a);db.flush();audit(db,"admin","absence.create",str(a.id));db.commit()
    return {"id":a.id,"status":a.status}
@app.post("/api/absences/{absence_id}/approve", dependencies=[Depends(admin)])
def approve(absence_id:int, db:Session=Depends(db)):
    a=db.get(Absence,absence_id)
    if not a: raise HTTPException(404,"Neprítomnosť neexistuje")
    a.status="approved";audit(db,"admin","absence.approve",str(a.id));db.commit()
    return {"status":a.status}
@app.get("/api/absences", dependencies=[Depends(admin)])
def absences(employee_id:Optional[int]=None,year:Optional[int]=None,db:Session=Depends(db)):
    q=select(Absence)
    if employee_id: q=q.where(Absence.employee_id==employee_id)
    if year:q=q.where(Absence.start<=date(year,12,31),Absence.end>=date(year,1,1))
    return [{"id":a.id,"employee_id":a.employee_id,"kind":a.kind,"start":a.start,"end":a.end,"minutes":a.minutes,"status":a.status,"note":a.note} for a in db.scalars(q).all()]
def working_dates(start:date,end:date):
    sk=holidays.country_holidays("SK", years=range(start.year,end.year+1))
    day=start
    while day<=end:
        if day.weekday()<5 and day not in sk:yield day
        day+=timedelta(days=1)
@app.get("/api/calendar/{year}", dependencies=[Depends(admin)])
def calendar(year:int):
    return [{"date":str(d),"name":n} for d,n in sorted(holidays.country_holidays("SK",years=[year]).items())]
@app.get("/api/balances/{employee_id}/{year}", dependencies=[Depends(admin)])
def balances(employee_id:int,year:int,db:Session=Depends(db)):
    e=db.get(Employee,employee_id)
    if not e: raise HTTPException(404,"Zamestnanec neexistuje")
    # Standard five-day model. Annual entitlement/proration needs HR validation.
    daily=Decimal(e.weekly_minutes)/Decimal(e.work_days)
    approved=db.scalars(select(Absence).where(Absence.employee_id==e.id,Absence.status=="approved",Absence.start<=date(year,12,31),Absence.end>=date(year,1,1))).all()
    def used(kind):
        total=Decimal(0)
        for a in approved:
            if a.kind!=kind:continue
            a_start=max(a.start,date(year,1,1)); a_end=min(a.end,date(year,12,31))
            total+=Decimal(a.minutes) if a.minutes is not None and a_start==a_end else daily*sum(1 for _ in working_dates(a_start,a_end))
        return int(total)
    doctor=used("doctor");accompany=used("accompany");vacation=used("vacation")
    return {"employee_id":e.id,"year":year,"daily_minutes_reference":float(daily),"vacation":{"illustrative_full_year_minutes":int(daily*e.work_days*e.annual_leave_weeks),"used_minutes":vacation,"requires_hr_confirmation":True},"doctor":{"statutory_reference_minutes":int(daily*7),"used_minutes":doctor,"remaining_reference_minutes":max(0,int(daily*7)-doctor)},"accompany":{"statutory_reference_minutes":int(daily*7),"used_minutes":accompany,"remaining_reference_minutes":max(0,int(daily*7)-accompany)},"note":"7 dní sa počíta podľa zákona na nevyhnutne potrebný čas; osobitné nároky, krátenie a odlišné rozvrhy treba vyhodnotiť individuálne."}
@app.get("/api/timesheet/{employee_id}", dependencies=[Depends(admin)])
def timesheet(employee_id:int,start:date,end:date,db:Session=Depends(db)):
    if (end-start).days>366 or end<start:raise HTTPException(400,"Maximálne 367 kalendárnych dní")
    e=db.get(Employee,employee_id)
    if not e:raise HTTPException(404,"Zamestnanec neexistuje")
    begin=datetime.combine(start,datetime.min.time(),TZ).astimezone(timezone.utc)
    finish=datetime.combine(end+timedelta(days=1),datetime.min.time(),TZ).astimezone(timezone.utc)
    events=db.scalars(select(Event).where(Event.employee_id==employee_id,Event.at>=begin,Event.at<finish).order_by(Event.at,Event.id)).all()
    pairs=[]; current=None;break_at=None; break_minutes=0; warnings=[]
    for ev in events:
        at=ev.at.replace(tzinfo=timezone.utc) if ev.at.tzinfo is None else ev.at
        if ev.kind=="in":
            if current: warnings.append(f"Duplicitný príchod {at.isoformat()}")
            current=at;break_at=None;break_minutes=0
        elif ev.kind=="break_start":
            if not current or break_at:warnings.append(f"Neplatná prestávka {at.isoformat()}")
            else:break_at=at
        elif ev.kind=="break_end":
            if break_at:break_minutes+=max(0,int((at-break_at).total_seconds()//60));break_at=None
            else:warnings.append(f"Koniec prestávky bez začiatku {at.isoformat()}")
        elif ev.kind=="out":
            if current:
                if break_at:break_minutes+=max(0,int((at-break_at).total_seconds()//60))
                gross=max(0,int((at-current).total_seconds()//60))
                pairs.append({"in":current.astimezone(TZ).isoformat(),"out":at.astimezone(TZ).isoformat(),"gross_minutes":gross,"break_minutes":break_minutes,"net_minutes":max(0,gross-break_minutes)})
                current=None;break_at=None;break_minutes=0
            else:warnings.append(f"Odchod bez príchodu {at.isoformat()}")
    if current:warnings.append("Neuzavretý príchod – nepočíta sa do odpracovaného času")
    net=sum(p["net_minutes"] for p in pairs)
    return {"employee_id":e.id,"from":start,"to":end,"pairs":pairs,"total_worked_minutes":net,"warnings":warnings,"note":"Saldo, nočná práca a príplatky vyžadujú konkrétny plán zmien; nie sú týmto reportom vypočítané."}
@app.get("/api/audit", dependencies=[Depends(admin)])
def audits(limit:int=Query(default=100,ge=1,le=500),db:Session=Depends(db)):
    return [{"at":x.at,"actor":x.actor,"action":x.action,"detail":x.detail} for x in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(limit)).all()]
