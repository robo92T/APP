"""HR workflows based on official Aktion manuals, implemented with BID-specific authorization.

Three phases:
  reviewed: employee verifies attendance (no lock)
  confirmed: manager/HR approves, freezes employee-period updates by these endpoints
  closed: existing global payroll month close remains the final authoritative lock

Bulk absences are explicit HR actions with validation, one DB transaction,
audit trail, duplicate/overlap protection and preview without writes.
"""
from datetime import date,datetime,timedelta,timezone
from typing import Optional,Literal
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel,Field
from sqlalchemy import DateTime, Date, ForeignKey, Integer, String, UniqueConstraint, select, func
from sqlalchemy.orm import Mapped,mapped_column,Session

KINDS={"vacation","doctor","accompany","doctor_unpaid","accompany_unpaid",
    "sick","ocr","maternity","paternity","parental","unpaid","paid_leave",
    "business_trip","training","wedding","funeral","blood_donation","other"}
NOTIFICATION={"ocr","sick","maternity","paternity","parental"}
class PeriodAction(BaseModel):
    employee_id:int
    year:int=Field(ge=2020,le=2100)
    month:int=Field(ge=1,le=12)
    note:str=Field(default="",max_length=350)
class BulkAbsence(BaseModel):
    employee_ids:list[int]=Field(min_length=1,max_length=150)
    kind:str
    start:date
    end:date
    minutes:Optional[int]=Field(default=None,ge=1,le=1440)
    reason:str=Field(min_length=8,max_length=400)
    dry_run:bool=True
def install(app,Base,Employee,Absence,engine,db,current_account,require_role,audit,is_closed_range):
    class EmployeeMonthReview(Base):
        __tablename__="employee_month_review"
        id:Mapped[int]=mapped_column(primary_key=True)
        employee_id:Mapped[int]=mapped_column(ForeignKey("employee.id"),index=True)
        year:Mapped[int]=mapped_column(Integer,index=True)
        month:Mapped[int]=mapped_column(Integer)
        reviewed_by:Mapped[Optional[str]]=mapped_column(String(80),nullable=True)
        reviewed_at:Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)
        confirmed_by:Mapped[Optional[str]]=mapped_column(String(80),nullable=True)
        confirmed_at:Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)
        note:Mapped[str]=mapped_column(String(350),default="")
        __table_args__=(UniqueConstraint("employee_id","year","month",name="uq_employee_month_review"),)
    Base.metadata.create_all(engine)
    def serialize(item):
        return {"employee_id":item.employee_id,"year":item.year,"month":item.month,
            "reviewed_by":item.reviewed_by,"reviewed_at":item.reviewed_at,
            "confirmed_by":item.confirmed_by,"confirmed_at":item.confirmed_at,"note":item.note,
            "status":"confirmed" if item.confirmed_at else "reviewed" if item.reviewed_at else "pending"}
    def scope(session,account,employee_id,manager_ok=True):
        if account.role in ("admin","hr"):return
        if account.employee_id==employee_id and account.role in ("employee","manager"):return
        if account.role=="manager" and manager_ok:
            from organization import direct_or_tree_report_ids
            if employee_id in direct_or_tree_report_ids(session,account.employee_id):return
        raise HTTPException(403,"Nemáš oprávnenie k dochádzke tejto osoby")
    def month_closed(session,year,month):
        from sqlalchemy import text
        return bool(session.execute(text("SELECT 1 FROM month_close WHERE year=:y AND month=:m"),
                      {"y":year,"m":month}).first())
    @app.get("/api/workflow/month/{year}/{month}",dependencies=[Depends(require_role("admin","hr"))])
    def monthly_status(year:int,month:int,session:Session=Depends(db)):
        if not 2020<=year<=2100 or not 1<=month<=12:raise HTTPException(422,"Neplatné obdobie")
        people=session.scalars(select(Employee).order_by(Employee.name)).all()
        entries={x.employee_id:x for x in session.scalars(select(EmployeeMonthReview).where(
            EmployeeMonthReview.year==year,EmployeeMonthReview.month==month)).all()}
        return {"year":year,"month":month,"closed":month_closed(session,year,month),
            "rows":[{"employee_id":p.id,"name":p.name,"status":serialize(entries[p.id]) if p.id in entries
                else {"status":"pending","reviewed_at":None,"confirmed_at":None,
                      "reviewed_by":None,"confirmed_by":None,"note":""}}
                for p in people if p.start_date<=date(year,month,28) and
                    (p.end_date is None or p.end_date>=date(year,month,1))]}
    @app.get("/api/workflow/my-month")
    def my_status(year:int=Query(ge=2020,le=2100),month:int=Query(ge=1,le=12),
        account=Depends(current_account),session:Session=Depends(db)):
        if account.employee_id is None:raise HTTPException(403,"Účet nie je priradený zamestnancovi")
        item=session.scalar(select(EmployeeMonthReview).where(
            EmployeeMonthReview.employee_id==account.employee_id,
            EmployeeMonthReview.year==year,EmployeeMonthReview.month==month))
        return serialize(item) if item else {"year":year,"month":month,"status":"pending"}
    @app.post("/api/workflow/review")
    def review(data:PeriodAction,account=Depends(current_account),session:Session=Depends(db)):
        scope(session,account,data.employee_id,manager_ok=False)
        if account.employee_id!=data.employee_id and account.role not in ("admin","hr"):
            raise HTTPException(403,"Zamestnanec môže kontrolovať iba vlastnú dochádzku")
        if month_closed(session,data.year,data.month):raise HTTPException(409,"Mesiac je uzavretý")
        item=session.scalar(select(EmployeeMonthReview).where(
            EmployeeMonthReview.employee_id==data.employee_id,
            EmployeeMonthReview.year==data.year,EmployeeMonthReview.month==data.month))
        if not item:
            item=EmployeeMonthReview(employee_id=data.employee_id,year=data.year,month=data.month)
            session.add(item)
        if item.confirmed_at:raise HTTPException(409,"Už potvrdenú dochádzku treba najprv odomknúť")
        item.reviewed_by=account.username;item.reviewed_at=datetime.now(timezone.utc)
        item.note=data.note
        audit(session,account.username,"attendance.review",f"{data.employee_id}:{data.year}-{data.month:02d}")
        session.commit();return serialize(item)
    @app.post("/api/workflow/confirm")
    def confirm(data:PeriodAction,account=Depends(current_account),session:Session=Depends(db)):
        if account.role not in ("manager","admin","hr"):raise HTTPException(403,"Potvrdzovať môže len vedúci alebo HR")
        if account.employee_id==data.employee_id:raise HTTPException(403,"Vlastnú dochádzku nemožno potvrdiť")
        if account.role=="manager":scope(session,account,data.employee_id,manager_ok=True)
        if month_closed(session,data.year,data.month):raise HTTPException(409,"Mesiac je uzavretý")
        item=session.scalar(select(EmployeeMonthReview).where(
            EmployeeMonthReview.employee_id==data.employee_id,
            EmployeeMonthReview.year==data.year,EmployeeMonthReview.month==data.month))
        if not item or not item.reviewed_at:raise HTTPException(409,"Najprv musí prebehnúť kontrola dochádzky")
        if item.confirmed_at:raise HTTPException(409,"Dochádzka je už potvrdená")
        item.confirmed_by=account.username;item.confirmed_at=datetime.now(timezone.utc)
        item.note=(item.note+" | "+data.note).strip(" |")[:350]
        audit(session,account.username,"attendance.confirm",f"{data.employee_id}:{data.year}-{data.month:02d}")
        session.commit();return serialize(item)
    @app.post("/api/workflow/unconfirm",dependencies=[Depends(require_role("admin","hr"))])
    def unconfirm(data:PeriodAction,actor=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        if len(data.note)<8:raise HTTPException(422,"Zadaj dôvod odomknutia (aspoň 8 znakov)")
        if month_closed(session,data.year,data.month):raise HTTPException(409,"Mesiac je už uzavretý, musí ho odomknúť administrátor")
        item=session.scalar(select(EmployeeMonthReview).where(
            EmployeeMonthReview.employee_id==data.employee_id,
            EmployeeMonthReview.year==data.year,EmployeeMonthReview.month==data.month))
        if not item or not item.confirmed_at:raise HTTPException(404,"Potvrdenie neexistuje")
        item.confirmed_at=None;item.confirmed_by=None;item.reviewed_at=None;item.reviewed_by=None
        item.note="ODOMKNUTÉ: "+data.note
        audit(session,actor.username,"attendance.unconfirm",f"{data.employee_id}:{data.year}-{data.month:02d} {data.note[:150]}")
        session.commit();return serialize(item)
    @app.get("/api/workflow/close-precheck/{year}/{month}",dependencies=[Depends(require_role("admin","hr"))])
    def close_precheck(year:int,month:int,session:Session=Depends(db)):
        if not 2020<=year<=2100 or not 1<=month<=12:raise HTTPException(422,"Neplatné obdobie")
        period_start=date(year,month,1)
        from calendar import monthrange
        period_end=date(year,month,monthrange(year,month)[1])
        people=session.scalars(select(Employee).where(
            Employee.start_date<=period_end,Employee.active==True)).all()
        entries={x.employee_id:x for x in session.scalars(select(EmployeeMonthReview).where(
            EmployeeMonthReview.year==year,EmployeeMonthReview.month==month)).all()}
        missing=[{"employee_id":p.id,"name":p.name,"reason":
            ("nepotvrdené" if p.id in entries and entries[p.id].reviewed_at else "neskontrolované")}
            for p in people if (not p.end_date or p.end_date>=period_start) and
            (p.id not in entries or not entries[p.id].confirmed_at)]
        return {"year":year,"month":month,"ready":not missing,"missing":missing,
                "note":"Kontrolný zoznam pred mzdovou uzávierkou. Aktuálna uzávierka zostáva samostatná."}
    @app.post("/api/bulk-absence",dependencies=[Depends(require_role("admin","hr"))])
    def bulk_absence(payload:BulkAbsence,actor=Depends(require_role("admin","hr")),
                     session:Session=Depends(db)):
        if payload.kind not in KINDS:raise HTTPException(422,"Neplatný druh neprítomnosti")
        if payload.end<payload.start or (payload.end-payload.start).days>366:
            raise HTTPException(422,"Neplatné obdobie")
        if len(set(payload.employee_ids))!=len(payload.employee_ids):
            raise HTTPException(422,"Duplicitní zamestnanci")
        if is_closed_range(session,payload.start,payload.end):
            raise HTTPException(409,"Obdobie zasahuje do uzavretého mesiaca")
        targets=session.scalars(select(Employee).where(Employee.id.in_(payload.employee_ids))).all()
        if len(targets)!=len(payload.employee_ids):raise HTTPException(404,"Niektorý zamestnanec neexistuje")
        if any(not e.active or e.start_date>payload.start or (e.end_date and e.end_date<payload.end) for e in targets):
            raise HTTPException(422,"Neaktívny zamestnanec alebo neprítomnosť mimo pracovného pomeru")
        # No partial writes: a single conflicting record rejects the entire batch.
        overlaps=session.scalars(select(Absence).where(
            Absence.employee_id.in_(payload.employee_ids),
            Absence.start<=payload.end,Absence.end>=payload.start,
            Absence.status.in_(("approved","pending")))).all()
        if overlaps:raise HTTPException(409,{"message":"Neprítomnosť sa prekrýva s existujúcim záznamom",
                                          "employee_ids":sorted({x.employee_id for x in overlaps})})
        review_rows=session.scalars(select(EmployeeMonthReview).where(
            EmployeeMonthReview.employee_id.in_(payload.employee_ids),
            EmployeeMonthReview.confirmed_at.isnot(None))).all()
        for row in review_rows:
            if date(row.year,row.month,1)<=payload.end and date(row.year,row.month,28)>=payload.start:
                raise HTTPException(409,"Dochádzka zamestnanca je už potvrdená")
        result={"dry_run":payload.dry_run,"count":len(targets),"employee_ids":payload.employee_ids,
            "kind":payload.kind,"start":payload.start,"end":payload.end}
        if payload.dry_run:return result
        for e in targets:
            session.add(Absence(employee_id=e.id,kind=payload.kind,start=payload.start,end=payload.end,
                minutes=payload.minutes,status="approved" if payload.kind in NOTIFICATION else "approved",
                note="Hromadný záznam HR: "+payload.reason))
        audit(session,actor.username,"absence.bulk",f"{len(targets)} people {payload.kind} {payload.start}:{payload.end} {payload.reason[:100]}")
        session.commit()
        return result
