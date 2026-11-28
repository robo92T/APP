"""Detailed HR employee profiles and shift templates, separate from legacy employee table.

Profile table avoids schema changes on existing SQLite databases. Authorize all writes
as admin/hr, reads as admin/hr/manager. No real employee data shipped in seeds.
"""
from datetime import date
from typing import Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Float, select
from work_rules import classify_agreement
from sqlalchemy.orm import Mapped, mapped_column, Session

class ProfileInput(BaseModel):
    personal_number: str = Field(min_length=1,max_length=32)
    title: str = Field(default="",max_length=40)
    first_name: str = Field(min_length=1,max_length=80)
    last_name: str = Field(min_length=1,max_length=80)
    email: str = Field(default="",max_length=160)
    phone: str = Field(default="",max_length=40)
    department: str = Field(default="",max_length=120)
    job_title: str = Field(default="",max_length=160)
    manager_id: Optional[int] = None
    work_regime: str = Field(default="fixed",max_length=40)
    fte: float = Field(default=1,gt=0,le=1)
    carryover_days: float = Field(default=0,ge=0,le=100)
    annual_leave_days: float = Field(default=25,ge=0,le=100)
    shift_template_id: Optional[int] = None
    weekly_minutes: int = Field(default=2400,ge=60,le=3600)
    work_days: int = Field(default=5,ge=1,le=7)
    start_date: date
    end_date: Optional[date] = None
    card_uid: Optional[str] = Field(default=None,max_length=128)
    active: bool = True

class TemplateInput(BaseModel):
    name: str = Field(min_length=2,max_length=100)
    start: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    end: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    break_minutes: int = Field(default=30,ge=0,le=240)
    work_days: int = Field(default=5,ge=1,le=7)
    description: str = Field(default="",max_length=250)

def install(app, Base, Employee, engine, db, require_role, audit):
    class Profile(Base):
        __tablename__="employee_profile"
        employee_id:Mapped[int]=mapped_column(ForeignKey("employee.id"),primary_key=True)
        personal_number:Mapped[str]=mapped_column(String(32),unique=True,index=True)
        title:Mapped[str]=mapped_column(String(40),default="")
        first_name:Mapped[str]=mapped_column(String(80),default="")
        last_name:Mapped[str]=mapped_column(String(80),default="")
        email:Mapped[str]=mapped_column(String(160),default="")
        phone:Mapped[str]=mapped_column(String(40),default="")
        department:Mapped[str]=mapped_column(String(120),default="")
        job_title:Mapped[str]=mapped_column(String(160),default="")
        manager_id:Mapped[Optional[int]]=mapped_column(ForeignKey("employee.id"),nullable=True)
        work_regime:Mapped[str]=mapped_column(String(40),default="fixed")
        fte:Mapped[float]=mapped_column(Float,default=1)
        carryover_days:Mapped[float]=mapped_column(Float,default=0)
        annual_leave_days:Mapped[float]=mapped_column(Float,default=25)
        shift_template_id:Mapped[Optional[int]]=mapped_column(Integer,nullable=True)
    class Template(Base):
        __tablename__="shift_template"
        id:Mapped[int]=mapped_column(primary_key=True)
        name:Mapped[str]=mapped_column(String(100),unique=True)
        start:Mapped[str]=mapped_column(String(5))
        end:Mapped[str]=mapped_column(String(5))
        break_minutes:Mapped[int]=mapped_column(Integer,default=30)
        work_days:Mapped[int]=mapped_column(Integer,default=5)
        description:Mapped[str]=mapped_column(String(250),default="")
        active:Mapped[bool]=mapped_column(Boolean,default=True)
    Base.metadata.create_all(engine)
    templates=[
      ("Pevný 07:30–15:30", "07:30","15:30",30,5,"Pevný režim; 7,5 h čistej práce denne"),
      ("Ranná 06:00–14:00", "06:00","14:00",30,5,"Ranná pracovná zmena"),
      ("Poobedná 14:00–22:00", "14:00","22:00",30,5,"Poobedná pracovná zmena"),
      ("Nočná 22:00–06:00", "22:00","06:00",30,5,"Cezpolnočná zmena – osobitné vyhodnotenie"),
      ("Pevný 08:00–16:30", "08:00","16:30",30,5,"8 h čistej práce denne"),
      ("Dispečer denná 06:00–18:00", "06:00","18:00",60,7,"11 h čistá práca, hodinová prestávka"),
      ("Dispečer nočná 18:00–06:00", "18:00","06:00",60,7,"11 h čistá práca, hodinová prestávka"),
      ("Dispečer polzmena 06:00–12:00", "06:00","12:00",0,7,"6 h pracovnej doby"),
    ]
    with Session(engine) as session:
        if session.scalar(select(Template.id).limit(1)) is None:
            session.add_all([Template(name=n,start=s,end=e,break_minutes=b,work_days=d,description=desc) for n,s,e,b,d,desc in templates])
            session.commit()
    def render_profile(e, p):
        return {"id":e.id,"personal_number":p.personal_number if p else str(e.id),
            "title":p.title if p else "","first_name":p.first_name if p else e.name.split(" ")[0],
            "last_name":p.last_name if p else " ".join(e.name.split(" ")[1:]),
            "name":e.name,"email":p.email if p else "","phone":p.phone if p else "",
            "department":p.department if p else "","job_title":p.job_title if p else "",
            "manager_id":p.manager_id if p else None,"work_regime":p.work_regime if p else "fixed",
            "fte":p.fte if p else 1,"carryover_days":p.carryover_days if p else 0,
            "annual_leave_days":p.annual_leave_days if p else e.annual_leave_weeks*e.work_days,
            "shift_template_id":p.shift_template_id if p else None,
            "weekly_minutes":e.weekly_minutes,"work_days":e.work_days,
            "start_date":e.start_date,"end_date":e.end_date,"card_uid":e.card_uid,"active":e.active}
    @app.get("/api/hr/employees",dependencies=[Depends(require_role("admin","hr"))])
    def hr_employees(session:Session=Depends(db)):
        people=session.scalars(select(Employee).order_by(Employee.name)).all()
        profile_map={p.employee_id:p for p in session.scalars(select(Profile)).all()}
        return [render_profile(e,profile_map.get(e.id)) for e in people]
    @app.get("/api/hr/employees/{employee_id}",dependencies=[Depends(require_role("admin","hr","manager"))])
    def hr_employee(employee_id:int,session:Session=Depends(db)):
        e=session.get(Employee,employee_id)
        if not e:raise HTTPException(404,"Zamestnanec neexistuje")
        return render_profile(e,session.get(Profile,employee_id))
    def save_profile(data:ProfileInput,session:Session,employee=None):
        if data.end_date and data.end_date<data.start_date:raise HTTPException(422,"Ukončenie pred nástupom")
        warning=classify_agreement(data.work_regime,data.weekly_minutes)
        if warning and data.work_regime in ("agreement_activity","agreement_student","agreement_seasonal"):
            raise HTTPException(422,warning)
        if data.manager_id and (not session.get(Employee,data.manager_id) or (employee and employee.id==data.manager_id)):
            raise HTTPException(422,"Neplatný nadriadený")
        if data.shift_template_id and not session.get(Template,data.shift_template_id):
            raise HTTPException(422,"Neznáma šablóna zmeny")
        prev=session.scalar(select(Profile).where(Profile.personal_number==data.personal_number))
        if prev and (employee is None or prev.employee_id!=employee.id):raise HTTPException(409,"Osobné číslo sa už používa")
        if data.card_uid:
            owner=session.scalar(select(Employee).where(Employee.card_uid==data.card_uid))
            if owner and (employee is None or owner.id!=employee.id):raise HTTPException(409,"RFID karta je už priradená")
        if employee is None:
            employee=Employee(name=data.first_name.strip()+" "+data.last_name.strip(),start_date=data.start_date)
            session.add(employee);session.flush()
        employee.name=data.first_name.strip()+" "+data.last_name.strip()
        employee.card_uid=data.card_uid or None
        employee.weekly_minutes=data.weekly_minutes
        employee.work_days=data.work_days
        employee.annual_leave_weeks=max(4,round(data.annual_leave_days/data.work_days))
        employee.start_date=data.start_date
        employee.end_date=data.end_date
        employee.active=data.active
        p=session.get(Profile,employee.id)
        if not p:p=Profile(employee_id=employee.id);session.add(p)
        for key in ("personal_number","title","first_name","last_name","email","phone","department","job_title","manager_id","work_regime","fte","carryover_days","annual_leave_days","shift_template_id"):
            setattr(p,key,getattr(data,key))
        return employee,p
    @app.post("/api/hr/employees",dependencies=[Depends(require_role("admin","hr"))],status_code=201)
    def create_employee(data:ProfileInput,session:Session=Depends(db)):
        e,_=save_profile(data,session)
        audit(session,"hr","employee.create",str(e.id));session.commit()
        return {"id":e.id}
    @app.put("/api/hr/employees/{employee_id}",dependencies=[Depends(require_role("admin","hr"))])
    def edit_employee(employee_id:int,data:ProfileInput,session:Session=Depends(db)):
        e=session.get(Employee,employee_id)
        if not e:raise HTTPException(404,"Zamestnanec neexistuje")
        save_profile(data,session,e)
        audit(session,"hr","employee.update",str(e.id));session.commit()
        return {"id":e.id,"updated":True}
    @app.get("/api/hr/shift-templates",dependencies=[Depends(require_role("admin","hr","manager"))])
    def shift_templates(session:Session=Depends(db)):
        return [{"id":x.id,"name":x.name,"start":x.start,"end":x.end,"break_minutes":x.break_minutes,"work_days":x.work_days,"description":x.description} for x in session.scalars(select(Template).where(Template.active==True).order_by(Template.id)).all()]
    @app.post("/api/hr/shift-templates",dependencies=[Depends(require_role("admin","hr"))],status_code=201)
    def create_template(data:TemplateInput,session:Session=Depends(db)):
        if session.scalar(select(Template).where(Template.name==data.name)):
            raise HTTPException(409,"Šablóna už existuje")
        obj=Template(**data.model_dump())
        session.add(obj);session.flush();audit(session,"hr","template.create",str(obj.id));session.commit()
        return {"id":obj.id}
 
    @app.get("/api/team/absences")
    def team_absences(account=Depends(require_role("admin","hr","manager")),session:Session=Depends(db)):
        """Managers may see pending requests only for directly assigned reports."""
        from main import Absence
        if account.role in ("admin","hr"):
            employee_ids=[e.id for e in session.scalars(select(Employee)).all()]
        elif account.employee_id is not None:
            from organization import direct_or_tree_report_ids
            employee_ids=list(direct_or_tree_report_ids(session,account.employee_id))
        else:
            employee_ids=[]
        if not employee_ids:return []
        people={e.id:e.name for e in session.scalars(select(Employee).where(Employee.id.in_(employee_ids))).all()}
        requests=session.scalars(select(Absence).where(Absence.employee_id.in_(employee_ids)).order_by(Absence.start.desc())).all()
        return [{"id":a.id,"employee_id":a.employee_id,"employee_name":people.get(a.employee_id,""),
                 "kind":a.kind,"start":a.start,"end":a.end,"minutes":a.minutes,
                 "status":a.status} for a in requests]
    @app.post("/api/team/absences/{absence_id}/{decision}")
    def decide_team_absence(absence_id:int,decision:str,account=Depends(require_role("admin","hr","manager")),session:Session=Depends(db)):
        from main import Absence, is_closed_range
        if decision not in ("approve","reject"):raise HTTPException(422,"Neplatné rozhodnutie")
        item=session.get(Absence,absence_id)
        if not item:raise HTTPException(404,"Žiadosť neexistuje")
        if item.status!="pending":raise HTTPException(409,"Žiadosť už nie je otvorená")
        if account.employee_id==item.employee_id:raise HTTPException(403,"Vlastnú žiadosť nemožno schváliť")
        if is_closed_range(session,item.start,item.end):raise HTTPException(409,"Obdobie je uzavreté")
        if account.role=="manager":
            if account.employee_id is None:raise HTTPException(403,"Vedúci nie je priradený zamestnancovi")
            from organization import direct_or_tree_report_ids
            if item.employee_id not in direct_or_tree_report_ids(session,account.employee_id):
                raise HTTPException(403,"Žiadosť nepatrí podriadenému")
        item.status="approved" if decision=="approve" else "rejected"
        audit(session,account.username,f"absence.{decision}",str(item.id))
        session.commit()
        return {"id":item.id,"status":item.status}
