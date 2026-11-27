"""Organizational tree, membership, and scoped manager access.

Based on functions from the uploaded BID prototype, implemented against the
existing SQLAlchemy data model to retain all current employee, audit and PDF
features. No destructive changes to existing profile tables.
"""
from typing import Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column, Session

_Unit=None
_Membership=None
_Profile=None

class UnitInput(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    parent_id:Optional[int]=None
    kind:str=Field(default="oddelenie",max_length=40)
    short:str=Field(default="",max_length=30)
    cost_center:str=Field(default="",max_length=40)
    manager_id:Optional[int]=None
    deputy_id:Optional[int]=None
    active:bool=True

class MembershipInput(BaseModel):
    employee_id:int
    unit_id:Optional[int]=None

def subtree_ids(session:Session,root_id:int):
    units=session.scalars(select(_Unit)).all()
    children={}
    for u in units:children.setdefault(u.parent_id,[]).append(u.id)
    visited=set();stack=[root_id]
    while stack:
        unit_id=stack.pop()
        if unit_id in visited:continue
        visited.add(unit_id)
        stack.extend(children.get(unit_id,[]))
    return visited

def direct_or_tree_report_ids(session:Session,manager_employee_id:int):
    """Return all reports below a managed unit, plus exceptional direct reports."""
    if _Unit is None:return set()
    units=session.scalars(select(_Unit)).all()
    roots=[u.id for u in units if u.manager_id==manager_employee_id or u.deputy_id==manager_employee_id]
    allowed_units=set()
    for root in roots:allowed_units.update(subtree_ids(session,root))
    reports={row.employee_id for row in session.scalars(
        select(_Membership).where(_Membership.unit_id.in_(allowed_units))
    ).all()} if allowed_units else set()
    if _Profile is not None:
        reports.update(p.employee_id for p in session.scalars(
            select(_Profile).where(_Profile.c.manager_id==manager_employee_id)
        ).all())
    reports.discard(manager_employee_id)
    return reports

def install(app,Base,Employee,engine,db,require_role,audit):
    global _Unit,_Membership,_Profile
    class OrgUnit(Base):
        __tablename__="org_unit"
        id:Mapped[int]=mapped_column(primary_key=True)
        name:Mapped[str]=mapped_column(String(160))
        parent_id:Mapped[Optional[int]]=mapped_column(ForeignKey("org_unit.id"),nullable=True)
        kind:Mapped[str]=mapped_column(String(40),default="oddelenie")
        short:Mapped[str]=mapped_column(String(30),default="")
        cost_center:Mapped[str]=mapped_column(String(40),default="")
        manager_id:Mapped[Optional[int]]=mapped_column(ForeignKey("employee.id"),nullable=True)
        deputy_id:Mapped[Optional[int]]=mapped_column(ForeignKey("employee.id"),nullable=True)
        active:Mapped[bool]=mapped_column(Boolean,default=True)
    class OrgMembership(Base):
        __tablename__="org_membership"
        employee_id:Mapped[int]=mapped_column(ForeignKey("employee.id"),primary_key=True)
        unit_id:Mapped[int]=mapped_column(ForeignKey("org_unit.id"),index=True)
    Base.metadata.create_all(engine)
    _Unit=OrgUnit;_Membership=OrgMembership
    _Profile=Base.metadata.tables.get("employee_profile")

    def serial(unit:OrgUnit,depth=0,member_count=0):
        return {"id":unit.id,"name":unit.name,"parent_id":unit.parent_id,
                "kind":unit.kind,"short":unit.short,"cost_center":unit.cost_center,
                "manager_id":unit.manager_id,"deputy_id":unit.deputy_id,
                "active":unit.active,"depth":depth,"employee_count":member_count}

    @app.get("/api/org/units",dependencies=[Depends(require_role("admin","hr"))])
    def units(session:Session=Depends(db)):
        all_units=session.scalars(select(OrgUnit).order_by(OrgUnit.name)).all()
        counts={}
        for m in session.scalars(select(OrgMembership)).all():
            counts[m.unit_id]=counts.get(m.unit_id,0)+1
        children={}
        for unit in all_units:children.setdefault(unit.parent_id,[]).append(unit)
        result=[];visited=set()
        def visit(item,depth):
            if item.id in visited:return
            visited.add(item.id);result.append(serial(item,depth,counts.get(item.id,0)))
            for child in children.get(item.id,[]):visit(child,depth+1)
        for root in children.get(None,[]):visit(root,0)
        for item in all_units:
            if item.id not in visited:visit(item,0)
        return result

    @app.post("/api/org/units",dependencies=[Depends(require_role("admin","hr"))])
    def create_unit(data:UnitInput,account=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        if data.parent_id is not None and not session.get(OrgUnit,data.parent_id):
            raise HTTPException(422,"Nadriadený útvar neexistuje")
        for eid in (data.manager_id,data.deputy_id):
            if eid is not None and not session.get(Employee,eid):raise HTTPException(422,"Neplatný vedúci alebo zástupca")
        item=OrgUnit(**data.model_dump())
        session.add(item);session.flush()
        audit(session,account.username,"org.create",str(item.id));session.commit()
        return serial(item)

    @app.put("/api/org/units/{unit_id}",dependencies=[Depends(require_role("admin","hr"))])
    def update_unit(unit_id:int,data:UnitInput,account=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        item=session.get(OrgUnit,unit_id)
        if not item:raise HTTPException(404,"Útvar neexistuje")
        if data.parent_id is not None:
            if not session.get(OrgUnit,data.parent_id):raise HTTPException(422,"Nadriadený útvar neexistuje")
            if data.parent_id in subtree_ids(session,unit_id):
                raise HTTPException(409,"Zmena by vytvorila cyklus v organizačnej štruktúre")
        for eid in (data.manager_id,data.deputy_id):
            if eid is not None and not session.get(Employee,eid):raise HTTPException(422,"Neplatný vedúci alebo zástupca")
        for key,value in data.model_dump().items():setattr(item,key,value)
        audit(session,account.username,"org.update",str(unit_id));session.commit()
        return serial(item)

    @app.delete("/api/org/units/{unit_id}",dependencies=[Depends(require_role("admin","hr"))])
    def delete_unit(unit_id:int,account=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        item=session.get(OrgUnit,unit_id)
        if not item:raise HTTPException(404,"Útvar neexistuje")
        if session.scalar(select(OrgUnit.id).where(OrgUnit.parent_id==unit_id)):
            raise HTTPException(409,"Útvar obsahuje podriadené útvary")
        if session.scalar(select(OrgMembership.employee_id).where(OrgMembership.unit_id==unit_id)):
            raise HTTPException(409,"Útvar obsahuje zamestnancov")
        session.delete(item);audit(session,account.username,"org.delete",str(unit_id));session.commit()
        return {"deleted":True}

    @app.get("/api/org/memberships",dependencies=[Depends(require_role("admin","hr"))])
    def memberships(session:Session=Depends(db)):
        return [{"employee_id":m.employee_id,"unit_id":m.unit_id} for m in session.scalars(select(OrgMembership)).all()]

    @app.put("/api/org/memberships",dependencies=[Depends(require_role("admin","hr"))])
    def assign_membership(data:MembershipInput,account=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        if not session.get(Employee,data.employee_id):raise HTTPException(404,"Zamestnanec neexistuje")
        if data.unit_id is not None and not session.get(OrgUnit,data.unit_id):
            raise HTTPException(404,"Útvar neexistuje")
        old=session.get(OrgMembership,data.employee_id)
        if data.unit_id is None:
            if old:session.delete(old)
        elif old:old.unit_id=data.unit_id
        else:session.add(OrgMembership(employee_id=data.employee_id,unit_id=data.unit_id))
        audit(session,account.username,"org.membership",f"{data.employee_id}:{data.unit_id}")
        session.commit()
        return {"saved":True}

    return OrgUnit,OrgMembership
