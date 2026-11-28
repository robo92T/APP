"""Audited HR payroll-time classifications, independent from employee punch records.

Categories describe what time was spent on. Only an explicit HR approved
non-overlapping OFFSITE classification may provide provisional credit toward
the daily work fund. Travel itself is not automatically worked time.
"""
from datetime import datetime,date,timezone
from typing import Optional,Literal
from zoneinfo import ZoneInfo
from fastapi import Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import Boolean,Date,DateTime,ForeignKey,Integer,String,select
from sqlalchemy.orm import Mapped,mapped_column,Session

TZ=ZoneInfo("Europe/Bratislava")
KINDS={
 "business_trip":"Služobná cesta","service_errand":"Služobné dôvody (vybavovanie mimo pracoviska)",
 "doctor":"Lekár","accompany":"Sprevádzanie","home_office":"Home office"}
MODES={"all_day","time_range","punched"}
PAYROLL_CREDIT_KINDS={"business_trip","service_errand","doctor","accompany"}
def get_mode_minutes(record,planned,worked):
    if record.mode=="all_day":return max(0,planned)
    if record.mode=="punched":return max(0,worked)
    if record.starts_at is None or record.ends_at is None:return 0
    start=record.starts_at.replace(tzinfo=timezone.utc) if record.starts_at.tzinfo is None else record.starts_at.astimezone(timezone.utc)
    end=record.ends_at.replace(tzinfo=timezone.utc) if record.ends_at.tzinfo is None else record.ends_at.astimezone(timezone.utc)
    return max(0,int((end-start).total_seconds()//60))

class NewComponent(BaseModel):
    employee_id:int=Field(gt=0)
    day:date
    kind:Literal["business_trip","service_errand","doctor","accompany","home_office"]
    mode:Literal["all_day","time_range","punched"]
    starts_at:Optional[datetime]=None
    ends_at:Optional[datetime]=None
    note:str=Field(min_length=8,max_length=400)
class VoidComponent(BaseModel):
    reason:str=Field(min_length=8,max_length=400)

def install(app,Base,Employee,engine,db,require_role,audit,is_closed_range):
    class WageComponent(Base):
        __tablename__="wage_component"
        id:Mapped[int]=mapped_column(primary_key=True)
        employee_id:Mapped[int]=mapped_column(ForeignKey("employee.id"),index=True)
        day:Mapped[date]=mapped_column(Date,index=True)
        kind:Mapped[str]=mapped_column(String(32))
        mode:Mapped[str]=mapped_column(String(20))
        starts_at:Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)
        ends_at:Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)
        note:Mapped[str]=mapped_column(String(400))
        active:Mapped[bool]=mapped_column(Boolean,default=True,index=True)
        created_by:Mapped[str]=mapped_column(String(80))
        created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
        cancelled_by:Mapped[Optional[str]]=mapped_column(String(80),nullable=True)
        cancelled_at:Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)
        cancellation_reason:Mapped[Optional[str]]=mapped_column(String(400),nullable=True)
    Base.metadata.create_all(engine)
    def serialize(x):
        return {"id":x.id,"employee_id":x.employee_id,"day":x.day,"kind":x.kind,"mode":x.mode,
            "starts_at":x.starts_at,"ends_at":x.ends_at,"note":x.note,"active":x.active,
            "created_by":x.created_by,"created_at":x.created_at,
            "cancelled_by":x.cancelled_by,"cancelled_at":x.cancelled_at,
            "cancellation_reason":x.cancellation_reason}
    @app.get("/api/wage-components",dependencies=[Depends(require_role("admin","hr"))])
    def list_components(year:int=Query(ge=2020,le=2100),month:int=Query(ge=1,le=12),
        employee_id:Optional[int]=None,session:Session=Depends(db)):
        from calendar import monthrange
        q=select(WageComponent).where(WageComponent.day>=date(year,month,1),
            WageComponent.day<=date(year,month,monthrange(year,month)[1]))
        if employee_id:q=q.where(WageComponent.employee_id==employee_id)
        return [serialize(x) for x in session.scalars(q.order_by(WageComponent.day.desc(),WageComponent.id.desc())).all()]
    @app.post("/api/wage-components",dependencies=[Depends(require_role("admin","hr"))],status_code=201)
    def create(data:NewComponent,actor=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        e=session.get(Employee,data.employee_id)
        if not e:raise HTTPException(404,"Zamestnanec neexistuje")
        if data.day<e.start_date or (e.end_date and data.day>e.end_date):
            raise HTTPException(422,"Dátum mimo pracovného pomeru")
        if is_closed_range(session,data.day,data.day):
            raise HTTPException(409,"Zvolený mesiac je uzavretý")
        start=end=None
        if data.mode=="time_range":
            if not data.starts_at or not data.ends_at or not data.starts_at.tzinfo or not data.ends_at.tzinfo:
                raise HTTPException(422,"Časová zložka vyžaduje začiatok, koniec a časové pásmo")
            start=data.starts_at.astimezone(timezone.utc);end=data.ends_at.astimezone(timezone.utc)
            if start>=end or end-start>__import__("datetime").timedelta(days=1):
                raise HTTPException(422,"Neplatný časový rozsah")
            if start.astimezone(TZ).date()!=data.day or (end-__import__("datetime").timedelta(microseconds=1)).astimezone(TZ).date()!=data.day:
                raise HTTPException(422,"Časový úsek musí byť v jednom lokálnom kalendárnom dni")
        elif data.starts_at or data.ends_at:
            raise HTTPException(422,"Pri celom dni alebo podľa pípnutí časové hodnoty nezadávaj")
        existing=session.scalars(select(WageComponent).where(
            WageComponent.employee_id==data.employee_id,WageComponent.day==data.day,
            WageComponent.active==True)).all()
        for other in existing:
            if other.kind==data.kind:
                raise HTTPException(409,"Táto mzdová zložka už existuje pre daný deň")
            if data.mode!="time_range" or other.mode!="time_range":
                raise HTTPException(409,"Celodenné a pípnutím odvodené zložky nemožno kombinovať s inou zložkou v ten istý deň")
            old_start=other.starts_at.replace(tzinfo=timezone.utc) if other.starts_at.tzinfo is None else other.starts_at.astimezone(timezone.utc)
            old_end=other.ends_at.replace(tzinfo=timezone.utc) if other.ends_at.tzinfo is None else other.ends_at.astimezone(timezone.utc)
            if start<old_end and end>old_start:
                raise HTTPException(409,"Časové úseky dvoch mzdových zložiek sa prekrývajú")
        item=WageComponent(employee_id=e.id,day=data.day,kind=data.kind,mode=data.mode,
            starts_at=start,ends_at=end,note=data.note,created_by=actor.username)
        session.add(item);session.flush()
        audit(session,actor.username,"wage_component.create",
              f"id={item.id};employee={e.id};day={data.day};kind={data.kind};mode={data.mode}")
        session.commit();return serialize(item)
    @app.post("/api/wage-components/{component_id}/cancel",dependencies=[Depends(require_role("admin","hr"))])
    def cancel(component_id:int,payload:VoidComponent,actor=Depends(require_role("admin","hr")),
        session:Session=Depends(db)):
        item=session.get(WageComponent,component_id)
        if not item or not item.active:raise HTTPException(404,"Aktívna zložka neexistuje")
        if is_closed_range(session,item.day,item.day):raise HTTPException(409,"Mesiac je uzavretý")
        item.active=False;item.cancelled_by=actor.username
        item.cancelled_at=datetime.now(timezone.utc);item.cancellation_reason=payload.reason
        audit(session,actor.username,"wage_component.cancel",
              f"id={item.id};reason={payload.reason[:170]}")
        session.commit();return serialize(item)
    return WageComponent
