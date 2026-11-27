"""Audited monthly HR close and CSV export, based on stored attendance data.

The close is an administrative lock for staff-facing writes. This is not a certified
payroll close: warnings and legal calculation rules must be reviewed manually.
"""
import csv
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import DateTime, Date, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column, Session

class ClosingError(Exception):
    pass

def install(app,Base,Employee,Absence,engine,db,require_role,audit,build_rows,Event,Shift):
    class MonthClose(Base):
        __tablename__="month_close"
        id:Mapped[int]=mapped_column(primary_key=True)
        year:Mapped[int]=mapped_column(Integer,index=True)
        month:Mapped[int]=mapped_column(Integer)
        closed_by:Mapped[str]=mapped_column(String(80))
        closed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
        __table_args__=(UniqueConstraint("year","month",name="uq_month_close"),)
    Base.metadata.create_all(engine)
    @app.get("/api/payroll/months",dependencies=[Depends(require_role("admin","hr"))])
    def payroll_months(session:Session=Depends(db)):
        return [{"year":m.year,"month":m.month,"closed_by":m.closed_by,"closed_at":m.closed_at} for m in session.scalars(select(MonthClose).order_by(MonthClose.year.desc(),MonthClose.month.desc())).all()]
    @app.post("/api/payroll/close/{year}/{month}")
    def close_month(year:int,month:int,account=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        if not 2020<=year<=2100 or not 1<=month<=12:raise HTTPException(422,"Neplatný rok alebo mesiac")
        if session.scalar(select(MonthClose).where(MonthClose.year==year,MonthClose.month==month)):
            raise HTTPException(409,"Mesiac je už uzavretý")
        session.add(MonthClose(year=year,month=month,closed_by=account.username))
        audit(session,account.username,"payroll.close",f"{year}-{month:02d}")
        session.commit()
        return {"year":year,"month":month,"locked":True,"note":"Administratívna uzávierka; vyžaduje kontrolu mzdárom"}
    @app.post("/api/payroll/reopen/{year}/{month}")
    def reopen(year:int,month:int,account=Depends(require_role("admin")),session:Session=Depends(db)):
        m=session.scalar(select(MonthClose).where(MonthClose.year==year,MonthClose.month==month))
        if not m:raise HTTPException(404,"Mesiac nie je uzavretý")
        session.delete(m);audit(session,account.username,"payroll.reopen",f"{year}-{month:02d}")
        session.commit()
        return {"year":year,"month":month,"locked":False}
    @app.get("/api/payroll/export.csv",dependencies=[Depends(require_role("admin","hr"))])
    def export_csv(year:int=Query(ge=2020,le=2100),month:int=Query(ge=1,le=12),session:Session=Depends(db)):
        tz=ZoneInfo("Europe/Bratislava")
        start=date(year,month,1)
        end=date(year,month,monthrange(year,month)[1])
        from_time=datetime.combine(start-timedelta(days=1),datetime.min.time(),tz).astimezone(timezone.utc)
        until_time=datetime.combine(end+timedelta(days=2),datetime.min.time(),tz).astimezone(timezone.utc)
        output=StringIO()
        writer=csv.writer(output,delimiter=";",lineterminator="\r\n")
        writer.writerow(["osobne_cislo_interny_id","meno","obdobie","fond_min","odpracovane_min","zapoctene_volno_min","saldo_min","upozornenia"])
        for employee in session.scalars(select(Employee).order_by(Employee.name)).all():
            events=session.scalars(select(Event).where(Event.employee_id==employee.id,Event.at>=from_time,Event.at<until_time).order_by(Event.at,Event.id)).all()
            absences=session.scalars(select(Absence).where(Absence.employee_id==employee.id,Absence.status=="approved",Absence.start<=end,Absence.end>=start)).all()
            shifts={s.day:s.planned_minutes for s in session.scalars(select(Shift).where(Shift.employee_id==employee.id,Shift.day>=start,Shift.day<=end)).all()}
            rows=build_rows(employee,events,shifts,absences,year,month)
            plan=sum(x["plan"] for x in rows);work=sum(x["worked"] for x in rows);credited=sum(x["credit"] for x in rows)
            warnings=sum(len(x["warnings"]) for x in rows)
            writer.writerow([employee.id,employee.name,f"{year}-{month:02d}",plan,work,credited,work+credited-plan,warnings])
        content=("\ufeff"+output.getvalue()).encode("utf-8")
        name=f"mzdy_dochadzka_{year}_{month:02d}.csv"
        return StreamingResponse(iter([content]),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{name}"',"Cache-Control":"no-store"})
    return MonthClose
