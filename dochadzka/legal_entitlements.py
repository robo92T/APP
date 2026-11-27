"""Validated reference tables for Slovak 2026 working-time leave.

Financial entitlements depend on contract, collective agreement and individual
circumstances. Do not infer sensitive family status from data; HR can explicitly
record an approved additional escort entitlement, without recording diagnosis.
"""
from datetime import date,timedelta
from calendar import monthrange
from typing import Optional
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel,Field
from sqlalchemy import ForeignKey,Integer,String,UniqueConstraint,select
from sqlalchemy.orm import Mapped,mapped_column,Session
from legal_calendar import is_workday,holiday_details

class ExtraEscortInput(BaseModel):
    extra_days:int=Field(ge=0,le=7)

def install(app,Base,Employee,Absence,Shift,engine,db,require_role,audit):
    class EscortEntitlement(Base):
        __tablename__="escort_entitlement"
        id:Mapped[int]=mapped_column(primary_key=True)
        employee_id:Mapped[int]=mapped_column(ForeignKey("employee.id"),index=True)
        year:Mapped[int]=mapped_column(Integer,index=True)
        extra_days:Mapped[int]=mapped_column(Integer,default=0)
        __table_args__=(UniqueConstraint("employee_id","year",name="uq_escort_year"),)
    Base.metadata.create_all(engine)
    @app.get("/api/legal/calendar/{year}",dependencies=[Depends(require_role("admin","hr"))])
    def statutory_calendar(year:int):
        if year<2020 or year>2100:raise HTTPException(422,"Neplatný rok")
        d=date(year,1,1);out=[]
        while d.year==year:
            detail=holiday_details(d)
            if detail["is_holiday_label"]:out.append(detail)
            d+=timedelta(days=1)
        return {"year":year,"holidays":out,
                "reference":"241/1993 Z. z.; Národný inšpektorát práce – usmernenie 2026",
                "warning":"Status dňa pracovného pokoja sa líši od statusu sviatku pre mzdové zvýhodnenie."}

    @app.put("/api/legal/employees/{employee_id}/escort/{year}",
             dependencies=[Depends(require_role("admin","hr"))])
    def set_extra_escort(employee_id:int,year:int,data:ExtraEscortInput,
                         actor=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        if not session.get(Employee,employee_id):raise HTTPException(404,"Zamestnanec neexistuje")
        if year<2026 or year>2100:raise HTTPException(422,"Neplatný rok")
        item=session.scalar(select(EscortEntitlement).where(EscortEntitlement.employee_id==employee_id,
            EscortEntitlement.year==year))
        if not item:
            item=EscortEntitlement(employee_id=employee_id,year=year,extra_days=data.extra_days);session.add(item)
        else:item.extra_days=data.extra_days
        audit(session,actor.username,"legal.escort.entitlement",f"{employee_id}:{year}:{data.extra_days}")
        session.commit()
        return {"employee_id":employee_id,"year":year,"additional_days":data.extra_days,
                "rule":"Len po overení individuálnych zákonných podmienok HR."}

    @app.get("/api/legal/employees/{employee_id}/{year}",dependencies=[Depends(require_role("admin","hr"))])
    def leave_reference(employee_id:int,year:int,session:Session=Depends(db)):
        if year<2020 or year>2100:raise HTTPException(422,"Neplatný rok")
        employee=session.get(Employee,employee_id)
        if not employee:raise HTTPException(404,"Zamestnanec neexistuje")
        daily=employee.weekly_minutes/max(1,employee.work_days)
        extra=session.scalar(select(EscortEntitlement).where(EscortEntitlement.employee_id==employee_id,
            EscortEntitlement.year==year))
        extra_days=extra.extra_days if extra else 0
        absences=session.scalars(select(Absence).where(
            Absence.employee_id==employee_id,Absence.status=="approved",
            Absence.start<=date(year,12,31),Absence.end>=date(year,1,1))).all()
        def used(kind):
            minutes=0;days=0
            for a in absences:
                if a.kind!=kind:continue
                first=max(a.start,date(year,1,1));last=min(a.end,date(year,12,31))
                if a.minutes is not None and first==last:
                    minutes+=a.minutes;days+=a.minutes/daily
                else:
                    d=first
                    while d<=last:
                        if is_workday(d):minutes+=int(daily);days+=1
                        d+=timedelta(days=1)
            return {"minutes":minutes,"reference_days":round(days,2)}
        doctor=used("doctor");escort=used("accompany");vacation=used("vacation")
        return {"employee_id":employee_id,"year":year,"reference_daily_minutes":daily,
                "doctor":{"limit_days":7,"limit_minutes":int(7*daily),"used":doctor,
                    "remaining_reference_minutes":max(0,int(7*daily)-doctor["minutes"])},
                "accompany":{"limit_days":7+extra_days,"base_days":7,
                    "additional_days_approved_by_hr":extra_days,"used":escort,
                    "remaining_reference_minutes":max(0,int((7+extra_days)*daily)-escort["minutes"])},
                "vacation":{"approved_reference_used":vacation,
                    "warning":"Ročný nárok, prenos a krátenie musia byť potvrdené HR podľa § 103–109 ZP."},
                "source":"§ 141 ods. 2 písm. a/c ZP – pravidlo 7 dní; ďalších 7 dní za splnených podmienok od 1.1.2026",
                "warning":"Ide o kontrolné limity, nie automatické potvrdenie nároku; čas potrebnosti, rozvrh a doklady musí overiť HR."}
