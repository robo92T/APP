"""FICTITIOUS preview data only. Never run this on persistent/production database.

Data is seeded only on an empty preview SQLite DB with DEMO_SEED=10 and
APP_ENV=preview.  No personal IDs, valid email domains or real RFID UIDs.
"""
import os
import random
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, insert, func
from sqlalchemy.orm import Session
from legal_calendar import is_workday

TZ=ZoneInfo("Europe/Bratislava")
NAMES=[
 ("Tamara","Vzorová","Personalistika a mzdy","personalistka",2250,1.0,25),
 ("Filip","Ukážkový","Ekonomika","finančný analytik",2250,1.0,25),
 ("Nina","Testovacia","Ekonomika","účtovníčka",2250,1.0,25),
 ("Adam","Demonštračný","IT a digitalizácia","správca aplikácií",2400,1.0,25),
 ("Laura","Fiktívna","IT a digitalizácia","IT koordinátorka",1200,0.5,25),
 ("Oliver","Modelový","Dispečing","dispečer",2250,1.0,25),
 ("Ema","Príkladová","Dispečing","dispečerka",2250,1.0,25),
 ("Samuel","Simulovaný","Dispečing","vedúci dispečingu",2250,1.0,25),
 ("Bianka","Neexistujúca","Zákaznícke centrum","referentka",2250,1.0,25),
 ("Jakub","Ilustračný","Zákaznícke centrum","vedúci tímu",2250,1.0,25),
]

def seed_preview(Base,engine,Employee,Event,Absence,Shift,audit):
    if os.getenv("APP_ENV")!="preview" or os.getenv("DEMO_SEED")!="10":
        return {"seeded":False,"reason":"disabled"}
    if engine.dialect.name!="sqlite":
        raise RuntimeError("Demo seed is forbidden on PostgreSQL")
    with Session(engine) as session:
        if session.scalar(select(func.count(Employee.id)))>0:
            return {"seeded":False,"reason":"employees already exist"}
        rng=random.Random(20261127)
        profiles=Base.metadata.tables.get("employee_profile")
        if profiles is None:
            raise RuntimeError("HR profile module must be installed before preview seed")
        created=[]
        for i,(first,last,dept,position,weekly,fte,leave) in enumerate(NAMES):
            e=Employee(name=first+" "+last,card_uid="DEMO-"+str(1001+i),
                weekly_minutes=weekly,work_days=5,annual_leave_weeks=5,
                start_date=date(2023,1,1),active=True)
            session.add(e);session.flush()
            created.append(e)
            session.execute(insert(profiles).values(employee_id=e.id,
                personal_number=f"D{1001+i}",first_name=first,last_name=last,
                title="",email=f"demo.{1001+i}@example.invalid",phone="",
                department=dept,job_title=position,work_regime="rotating" if dept=="Dispečing" else "fixed",
                fte=fte,carryover_days=2 if i%3==0 else 0,
                annual_leave_days=leave,shift_template_id=None))
        # Manager relationships only for demo visual inspection.
        for subordinate in (created[5],created[6]):
            session.execute(profiles.update().where(profiles.c.employee_id==subordinate.id).values(manager_id=created[7].id))
        session.execute(profiles.update().where(profiles.c.employee_id==created[8].id).values(manager_id=created[9].id))
        begin=date(2026,11,1)
        end=date(2026,11,27)
        d=begin
        while d<=end:
            for i,e in enumerate(created):
                if i in (5,6,7):
                    # 24/7 demonstration with staggered day/night/free cycles.
                    k=(d-begin).days+i
                    slot=k%4
                    if slot>=2:continue
                    start_t=time(6,0) if slot==0 else time(18,0)
                    end_t=time(18,0) if slot==0 else time(6,0)
                    plan=720
                else:
                    if not is_workday(d):continue
                    start_t=time(7,30) if i%3 else time(8,0)
                    end_t=time(15,30) if i%3 else time(16,0)
                    plan=450 if e.weekly_minutes>=2250 else 240
                session.add(Shift(employee_id=e.id,day=d,planned_minutes=plan,
                    start_time=start_t.strftime("%H:%M"),end_time=end_t.strftime("%H:%M"),
                    note="DEMO · automaticky vytvorená plánovaná zmena"))
                # Leave days retain their scheduled time, but no punch is simulated.
                if i==0 and d in (date(2026,11,12),date(2026,11,13)):continue
                if i==1 and d==date(2026,11,19):continue
                if i in (5,6,7):
                    actual_start=datetime.combine(d,start_t,TZ)
                    actual_end=datetime.combine(d+(timedelta(days=1) if slot==1 else timedelta(0)),end_t,TZ)
                else:
                    deviation=rng.choice([-12,-5,0,0,3,7,18])
                    actual_start=datetime.combine(d,start_t,TZ)+timedelta(minutes=deviation)
                    actual_end=datetime.combine(d,end_t,TZ)+timedelta(minutes=rng.choice([0,5,8,12,15,20]))
                for kind,ts in (("in",actual_start),("out",actual_end)):
                    session.add(Event(employee_id=e.id,kind=kind,at=ts.astimezone(timezone.utc),origin="demo",device_id="DEMO-VIRTUAL"))
            d+=timedelta(days=1)
        for e,kind,start,end,minutes in [
            (created[0],"vacation",date(2026,11,12),date(2026,11,13),None),
            (created[1],"doctor",date(2026,11,19),date(2026,11,19),120),
            (created[2],"accompany",date(2026,11,26),date(2026,11,26),150),
            (created[3],"ocr",date(2026,11,23),date(2026,11,24),None),
            (created[4],"vacation",date(2026,12,10),date(2026,12,11),None),
        ]:
            session.add(Absence(employee_id=e.id,kind=kind,start=start,end=end,minutes=minutes,
                status="pending" if start.month==12 else "approved",
                note="FIKTÍVNE TESTOVACIE ÚDAJE"))
        org_table=Base.metadata.tables.get("org_unit")
        org_members=Base.metadata.tables.get("org_membership")
        if org_table is not None and org_members is not None:
            root=session.execute(insert(org_table).values(name="BID DEMO – spoločnosť",
                short="BID",kind="spoločnosť",cost_center="000",
                active=True)).inserted_primary_key[0]
            ids={}
            for dept,short,center in [
                ("Personalistika a mzdy","HR","110"),("Ekonomika","EKO","120"),
                ("IT a digitalizácia","IT","130"),("Dispečing","DIS","210"),
                ("Zákaznícke centrum","ZC","220")]:
                manager={"Dispečing":created[7].id,"Zákaznícke centrum":created[9].id}.get(dept)
                ids[dept]=session.execute(insert(org_table).values(name=dept,short=short,
                    kind="oddelenie",parent_id=root,manager_id=manager,
                    cost_center=center,active=True)).inserted_primary_key[0]
            for i,(_,_,dept,_,_,_,_) in enumerate(NAMES):
                session.execute(insert(org_members).values(employee_id=created[i].id,unit_id=ids[dept]))
        audit(session,"system","demo.seed","10 fictional employees, November 2026")
        session.commit()
        return {"seeded":True,"employees":len(created)}
