"""Slovak domestic business travel and daily meal entitlement (informational HR calculations).

Legislative reference: §152 Labour Code, Act 283/2002 §§4–7, Notice
280/2025 from 2025-12-01 and 255/2026 from 2026-12-01.
No foreign travel automation: foreign currencies, border crossing and
country-specific rates require a dedicated verified travel module.
"""
import csv
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from io import BytesIO, StringIO
from typing import Optional, Literal
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column, Session

TZ=ZoneInfo("Europe/Bratislava")
RATES=[
    (date(2025,12,1),Decimal("9.30"),Decimal("13.80"),Decimal("20.60"),"280/2025 Z. z."),
    (date(2026,12,1),Decimal("9.80"),Decimal("14.60"),Decimal("21.70"),"255/2026 Z. z."),
]
CAR_PER_KM_2026=Decimal("0.313") # from 2026-01-01, Notice 340/2025
MEAL_SOURCES=[
    "https://www.ip.gov.sk/pracovnopravne-vztahy/pracovne-cesty/sumy-stravneho-od-1-decembra-2026.html",
    "https://www.ip.gov.sk/pracovnopravne-vztahy/socialna-politika-zamestnavatela-pracovne-podmienky-osobitnych-skupin-zamestnancov/sumy-stravneho-od-1-decembra-2025.html",
    "https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2002/283/",
    "https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2001/311/"
]
def money(amount):return Decimal(amount).quantize(Decimal("0.01"),rounding=ROUND_CEILING)
def safe_csv_cell(value):
    # Prevent spreadsheet formula injection in exported employee names and free text.
    if isinstance(value,str) and value.startswith(("=","+","-","@","\\t","\\r","\\n")):
        return "'"+value
    return value

def applicable_rates(day):
    found=[item for item in RATES if day>=item[0]]
    if not found:raise ValueError("Chýba overená zákonná sadzba pre zvolený dátum.")
    return found[-1]
def to_utc(value):
    # Database drivers, especially SQLite, may drop UTC tzinfo on roundtrip.
    # User input itself is validated as offset-aware before persistence.
    if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
def daily_intervals(start,end):
    cursor=to_utc(start);stop=to_utc(end)
    if stop<=cursor:raise ValueError("Koniec cesty musí nasledovať po začiatku.")
    if stop-cursor>timedelta(days=31):raise ValueError("Jedna pracovná cesta môže trvať najviac 31 dní.")
    while cursor<stop:
        local_day=cursor.astimezone(TZ).date()
        next_day=datetime.combine(local_day+timedelta(days=1),time.min,TZ).astimezone(timezone.utc)
        limit=min(stop,next_day)
        yield local_day,int((limit-cursor).total_seconds()//60)
        cursor=limit
def compute_domestic_day(day,minutes,breakfast=False,lunch=False,dinner=False,rate_override=None):
    first,mid,high=rate_override or applicable_rates(day)[1:4]
    band=first if 300<=minutes<=720 else mid if 720<minutes<=1080 else high if minutes>1080 else Decimal("0")
    top=high
    percent=(Decimal("0.25") if breakfast else 0)+(Decimal("0.40") if lunch else 0)+(Decimal("0.35") if dinner else 0)
    # Round only final payable amount, for each calendar day, to nearest cent upwards.
    deduction=top*percent
    payable=money(max(Decimal("0"),band-deduction))
    return {"day":day.isoformat(),"minutes":minutes,"hours":round(minutes/60,2),
        "band":("5–12 h" if 300<=minutes<=720 else "nad 12–18 h" if 720<minutes<=1080 else "nad 18 h" if minutes>1080 else "menej než 5 h"),
        "gross_eur":float(band),"deduction_reference_eur":float(deduction),
        "meal_allowance_eur":float(payable),"provided_meals":{"breakfast":breakfast,"lunch":lunch,"dinner":dinner},
        "law":applicable_rates(day)[4],
        "note":"Krátenie vychádza z najvyššieho pásma; zohľadnite nevyužiteľné bezplatné jedlá."}
class TripInput(BaseModel):
    employee_id:int
    purpose:str=Field(min_length=5,max_length=250)
    destination:str=Field(min_length=2,max_length=180)
    starts_at:datetime
    ends_at:datetime
    transport:Literal["public","company_car","private_car","other"]="public"
    private_car_km:Decimal=Field(default=Decimal("0"),ge=0,le=50000)
    fuel_l_per_100km:Decimal=Field(default=Decimal("0"),ge=0,le=50)
    fuel_price_eur_l:Decimal=Field(default=Decimal("0"),ge=0,le=10)
    public_transport_eur:Decimal=Field(default=Decimal("0"),ge=0,le=100000)
    lodging_eur:Decimal=Field(default=Decimal("0"),ge=0,le=100000)
    other_expenses_eur:Decimal=Field(default=Decimal("0"),ge=0,le=100000)
    advance_eur:Decimal=Field(default=Decimal("0"),ge=0,le=100000)
    note:str=Field(default="",max_length=400)
class MealsInput(BaseModel):
    day:date
    breakfast:bool=False
    lunch:bool=False
    dinner:bool=False
    cannot_use_provided:bool=False
class Confirm(BaseModel):
    reason:str=Field(min_length=8,max_length=400)
def install(app,Base,Employee,Event,Absence,Shift,engine,db,require_role,audit,is_closed_range,get_approved_legal_rules=None):
    from pdf_reports import build_rows
    class TravelOrder(Base):
        __tablename__="travel_order"
        id:Mapped[int]=mapped_column(primary_key=True)
        employee_id:Mapped[int]=mapped_column(ForeignKey("employee.id"),index=True)
        purpose:Mapped[str]=mapped_column(String(250))
        destination:Mapped[str]=mapped_column(String(180))
        starts_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
        ends_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
        transport:Mapped[str]=mapped_column(String(25),default="public")
        private_car_km:Mapped[Decimal]=mapped_column(Numeric(12,2),default=0)
        fuel_l_per_100km:Mapped[Decimal]=mapped_column(Numeric(8,3),default=0)
        fuel_price_eur_l:Mapped[Decimal]=mapped_column(Numeric(8,3),default=0)
        public_transport_eur:Mapped[Decimal]=mapped_column(Numeric(12,2),default=0)
        lodging_eur:Mapped[Decimal]=mapped_column(Numeric(12,2),default=0)
        other_expenses_eur:Mapped[Decimal]=mapped_column(Numeric(12,2),default=0)
        advance_eur:Mapped[Decimal]=mapped_column(Numeric(12,2),default=0)
        status:Mapped[str]=mapped_column(String(25),default="draft")
        created_by:Mapped[str]=mapped_column(String(80))
        approved_by:Mapped[Optional[str]]=mapped_column(String(80),nullable=True)
        approved_at:Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)
        note:Mapped[str]=mapped_column(String(400),default="")
    class TravelMeal(Base):
        __tablename__="travel_meal"
        id:Mapped[int]=mapped_column(primary_key=True)
        trip_id:Mapped[int]=mapped_column(ForeignKey("travel_order.id"),index=True)
        day:Mapped[date]=mapped_column(Date,index=True)
        breakfast:Mapped[bool]=mapped_column(Boolean,default=False)
        lunch:Mapped[bool]=mapped_column(Boolean,default=False)
        dinner:Mapped[bool]=mapped_column(Boolean,default=False)
        cannot_use_provided:Mapped[bool]=mapped_column(Boolean,default=False)
    Base.metadata.create_all(engine)
    def rate_for_date(session,day):
        original=applicable_rates(day)
        if day<date(2026,12,1) or get_approved_legal_rules is None:
            return original[1:4]
        values=get_approved_legal_rules(session,day)
        return tuple(Decimal(values[key])/100 for key in
            ("domestic_5_12_cents","domestic_12_18_cents","domestic_over18_cents"))
    def mileage_for_date(session,day):
        if day<date(2026,12,1) or get_approved_legal_rules is None:
            return CAR_PER_KM_2026
        return Decimal(get_approved_legal_rules(session,day)["private_car_milleuro_km"])/1000
    def serialize(t,session):
        provided={m.day:m for m in session.scalars(select(TravelMeal).where(TravelMeal.trip_id==t.id)).all()}
        lines=[]
        for day,minutes in daily_intervals(t.starts_at,t.ends_at):
            m=provided.get(day)
            waive=bool(m and m.cannot_use_provided)
            lines.append(compute_domestic_day(day,minutes,
                bool(m and m.breakfast and not waive),
                bool(m and m.lunch and not waive),
                bool(m and m.dinner and not waive),rate_override=rate_for_date(session,day)))
        allowance=sum((Decimal(str(x["meal_allowance_eur"])) for x in lines),Decimal(0))
        mileage=Decimal(0);fuel=Decimal(0)
        warnings=[]
        if t.transport=="private_car":
            if to_utc(t.starts_at).astimezone(TZ).date()<date(2026,1,1):
                warnings.append("Kilometrová sadzba pred 1.1.2026 nie je v systéme overená.")
            else:mileage=Decimal(t.private_car_km)*mileage_for_date(session,to_utc(t.starts_at).astimezone(TZ).date())
            fuel=Decimal(t.private_car_km)*Decimal(t.fuel_l_per_100km)*Decimal(t.fuel_price_eur_l)/100
            if fuel==0:warnings.append("Doplň spotrebu a cenu paliva podľa dokladov a technického preukazu.")
        if t.transport not in ("private_car","public"):
            if t.private_car_km: warnings.append("Kilometrovné je evidované, ale doprava nie je súkromným vozidlom.")
        expenses=money(t.public_transport_eur+t.lodging_eur+t.other_expenses_eur)
        travel_total=money(allowance+mileage+fuel+expenses)
        settlement=money(travel_total-Decimal(t.advance_eur)) if travel_total>=Decimal(t.advance_eur) else -money(Decimal(t.advance_eur)-travel_total)
        return {"id":t.id,"employee_id":t.employee_id,"employee_name":session.get(Employee,t.employee_id).name,
            "purpose":t.purpose,"destination":t.destination,
            "starts_at":t.starts_at,"ends_at":t.ends_at,"status":t.status,
            "transport":t.transport,"note":t.note,"created_by":t.created_by,"approved_by":t.approved_by,
            "meal_days":lines,"meal_allowance_eur":float(money(allowance)),
            "mileage_eur":float(money(mileage)),"fuel_eur":float(money(fuel)),
            "expenses_eur":float(expenses),"travel_total_eur":float(travel_total),
            "advance_eur":float(t.advance_eur),"to_pay_eur":float(settlement),
            "warnings":warnings,
            "note_calculation":"Orientačné tuzemské náhrady. Čas pracovnej cesty nie je automaticky odpracovaným časom."}
    def ensure_valid(payload,session):
        if payload.starts_at.tzinfo is None or payload.ends_at.tzinfo is None:
            raise HTTPException(422,"Uveď časové pásmo pri začiatku aj konci pracovnej cesty")
        start=to_utc(payload.starts_at);end=to_utc(payload.ends_at)
        if end<=start or end-start>timedelta(days=31):raise HTTPException(422,"Neplatná dĺžka cesty (max. 31 dní)")
        employee=session.get(Employee,payload.employee_id)
        if not employee:raise HTTPException(404,"Zamestnanec neexistuje")
        begin=start.astimezone(TZ).date();finish=end.astimezone(TZ).date()
        if is_closed_range(session,begin,finish):raise HTTPException(409,"Zvolený mesiac je uzavretý")
        if employee.start_date>begin or (employee.end_date and employee.end_date<finish):
            raise HTTPException(422,"Pracovná cesta mimo pracovného pomeru")
        return employee,start,end
    @app.get("/api/travel",dependencies=[Depends(require_role("admin","hr"))])
    def trips(session:Session=Depends(db)):
        return [serialize(x,session) for x in session.scalars(select(TravelOrder).order_by(TravelOrder.id.desc()).limit(250)).all()]
    @app.post("/api/travel",dependencies=[Depends(require_role("admin","hr"))])
    def create(data:TripInput,actor=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        employee,start,end=ensure_valid(data,session)
        conflicts=session.scalars(select(TravelOrder).where(
            TravelOrder.employee_id==data.employee_id,
            TravelOrder.status!="cancelled")).all()
        if any(to_utc(x.starts_at)<end and to_utc(x.ends_at)>start for x in conflicts):
            raise HTTPException(409,"Pracovná cesta sa prekrýva s existujúcou cestou")
        t=TravelOrder(**data.model_dump(exclude={"employee_id","starts_at","ends_at"}),
            employee_id=employee.id,starts_at=start,ends_at=end,created_by=actor.username)
        session.add(t);session.flush()
        audit(session,actor.username,"travel.create",str(t.id));session.commit()
        return serialize(t,session)
    @app.put("/api/travel/{trip_id}/meal",dependencies=[Depends(require_role("admin","hr"))])
    def update_meal(trip_id:int,data:MealsInput,actor=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        t=session.get(TravelOrder,trip_id)
        if not t:raise HTTPException(404,"Cesta neexistuje")
        if t.status!="draft":raise HTTPException(409,"Schválené vyúčtovanie nie je možné meniť")
        days={d for d,_ in daily_intervals(t.starts_at,t.ends_at)}
        if data.day not in days:raise HTTPException(422,"Deň neleží v období cesty")
        if is_closed_range(session,data.day,data.day):raise HTTPException(409,"Mesiac uzavretý")
        existing=session.scalar(select(TravelMeal).where(TravelMeal.trip_id==trip_id,TravelMeal.day==data.day))
        if existing is None:existing=TravelMeal(trip_id=trip_id,day=data.day);session.add(existing)
        for key in ("breakfast","lunch","dinner","cannot_use_provided"):setattr(existing,key,getattr(data,key))
        audit(session,actor.username,"travel.meal",f"{trip_id}:{data.day}")
        session.commit();return serialize(t,session)
    @app.post("/api/travel/{trip_id}/approve",dependencies=[Depends(require_role("admin","hr"))])
    def approve(trip_id:int,data:Confirm,actor=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        t=session.get(TravelOrder,trip_id)
        if not t:raise HTTPException(404,"Cesta neexistuje")
        if t.status!="draft":raise HTTPException(409,"Cesta už je schválená alebo zrušená")
        if t.created_by==actor.username and actor.role!="admin":
            raise HTTPException(403,"Vlastné vyúčtovanie musí overiť iná osoba")
        t.status="approved";t.approved_by=actor.username;t.approved_at=datetime.now(timezone.utc)
        audit(session,actor.username,"travel.approve",f"{t.id}:{data.reason[:180]}")
        session.commit();return serialize(t,session)
    @app.post("/api/travel/{trip_id}/cancel",dependencies=[Depends(require_role("admin","hr"))])
    def cancel(trip_id:int,data:Confirm,actor=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        t=session.get(TravelOrder,trip_id)
        if not t:raise HTTPException(404,"Cesta neexistuje")
        if t.status=="cancelled":raise HTTPException(409,"Cesta je už zrušená")
        if is_closed_range(session,to_utc(t.starts_at).astimezone(TZ).date(),to_utc(t.ends_at).astimezone(TZ).date()):
            raise HTTPException(409,"Cesta patrí do uzavretého obdobia")
        t.status="cancelled"
        audit(session,actor.username,"travel.cancel",f"{t.id}:{data.reason[:200]}")
        session.commit();return {"id":t.id,"status":"cancelled"}
    @app.get("/api/meals/month",dependencies=[Depends(require_role("admin","hr"))])
    def meal_month(year:int=Query(ge=2025,le=2100),month:int=Query(ge=1,le=12),session:Session=Depends(db)):
        begin=date(year,month,1);end=date(year,month,monthrange(year,month)[1])
        start_utc=datetime.combine(begin-timedelta(days=1),time.min,TZ).astimezone(timezone.utc)
        stop_utc=datetime.combine(end+timedelta(days=2),time.min,TZ).astimezone(timezone.utc)
        employees=session.scalars(select(Employee).order_by(Employee.name)).all()
        trips=session.scalars(select(TravelOrder).where(TravelOrder.status=="approved")).all()
        relevant=[t for t in trips if to_utc(t.starts_at).astimezone(TZ).date()<=end and
                  to_utc(t.ends_at).astimezone(TZ).date()>=begin]
        travel_by={}
        for t in relevant:
            for d,mins in daily_intervals(t.starts_at,t.ends_at):
                if begin<=d<=end:travel_by.setdefault((t.employee_id,d),[]).append((t,mins))
        people=[]
        for emp in employees:
            if emp.start_date>end or (emp.end_date and emp.end_date<begin):continue
            punch=session.scalars(select(Event).where(Event.employee_id==emp.id,Event.at>=start_utc,
                Event.at<stop_utc).order_by(Event.at,Event.id)).all()
            shifts={x.day:x for x in session.scalars(select(Shift).where(
                Shift.employee_id==emp.id,Shift.day>=begin-timedelta(days=1),Shift.day<=end)).all()}
            absences=session.scalars(select(Absence).where(Absence.employee_id==emp.id,
                Absence.start<=end,Absence.end>=begin,Absence.status=="approved")).all()
            rows=build_rows(emp,punch,shifts,absences,year,month)
            days=[];count=0;allowance=Decimal("0")
            for r in rows:
                d=r["day"]
                if d<emp.start_date or (emp.end_date and d>emp.end_date):continue
                trip_for_day=travel_by.get((emp.id,d),[])
                trip_min=sum(x[1] for x in trip_for_day)
                trip_allowance=Decimal("0")
                for t,_ in trip_for_day:
                    calculated=serialize(t,session)
                    trip_allowance+=sum(Decimal(str(x["meal_allowance_eur"])) for x in calculated["meal_days"] if x["day"]==d.isoformat())
                # Caveat: worked time can span workplaces. Unless explicitly recorded,
                # a day with travel and >4h work cannot prove that work occurred at REGULAR workplace.
                if trip_for_day:
                    status="requires_regular_workplace_review" if r["worked"]>240 else "travel_allowance_only"
                    eligible=False
                elif r["worked"]>240:
                    status="eligible"
                    eligible=True
                elif r["worked"]==0 and r["plan"]>0 and any(a.kind=="business_trip" and a.start<=d<=a.end for a in absences):
                    status="travel_details_missing"
                    eligible=False
                else:
                    status="not_eligible"
                    eligible=False
                if eligible:count+=1
                allowance+=trip_allowance
                rate=(None,*rate_for_date(session,d))
                days.append({"day":d.isoformat(),"worked_minutes":r["worked"],
                    "planned_minutes":r["plan"],"trip_minutes":trip_min,
                    "meal_ticket_status":status,"meal_ticket_eligible":eligible,
                    "tickets":1 if eligible else 0,"trip_meal_eur":float(money(trip_allowance)),
                    "ticket_min_value_eur":float(money(rate[1]*Decimal("0.75"))),
                    "employer_min_eur":float(money(money(rate[1]*Decimal("0.75"))*Decimal("0.55"))),
                    "note":"Pri ceste je potrebné overiť prácu >4h na pravidelnom pracovisku" if status=="requires_regular_workplace_review" else ""})
            people.append({"employee_id":emp.id,"name":emp.name,"meal_ticket_days":count,
                "trip_meal_eur":float(money(allowance)),"days":days})
        return {"year":year,"month":month,"employees":people,
            "total_tickets":sum(p["meal_ticket_days"] for p in people),
            "travel_meals_eur":float(money(sum(Decimal(str(p["trip_meal_eur"])) for p in people))),
            "note":"Kontrolný výpočet. Práca >4h na pravidelnom pracovisku pri služobnej ceste a nároky pri iných neprítomnostiach vyžadujú potvrdenie HR."}
    @app.get("/api/meals/month.csv",dependencies=[Depends(require_role("admin","hr"))])
    def meal_month_csv(year:int=Query(ge=2025,le=2100),month:int=Query(ge=1,le=12),
                       session:Session=Depends(db)):
        calculated=meal_month(year,month,session)
        buf=StringIO()
        writer=csv.writer(buf,delimiter=";",lineterminator="\r\n")
        writer.writerow(["Zamestnanec","Dátum","Odpracované min","Fond min","Služobná cesta min",
            "Nárok na stravovací lístok","Počet lístkov","Stravné z pracovnej cesty EUR",
            "Minimálna hodnota poukážky EUR","Minimálny príspevok zamestnávateľa EUR","Poznámka"])
        for person in calculated["employees"]:
            for day in person["days"]:
                writer.writerow([safe_csv_cell(value) for value in [
                    person["name"],day["day"],day["worked_minutes"],
                    day["planned_minutes"],day["trip_minutes"],day["meal_ticket_status"],
                    day["tickets"],day["trip_meal_eur"],day["ticket_min_value_eur"],
                    day["employer_min_eur"],day["note"]]])
        payload=("\ufeff"+buf.getvalue()).encode("utf-8")
        return StreamingResponse(iter([payload]),media_type="text/csv; charset=utf-8",
            headers={"Cache-Control":"no-store",
                "Content-Disposition":f'attachment; filename="bid_stravne_{year}_{month:02d}.csv"'})

    @app.get("/api/travel/summary.csv",dependencies=[Depends(require_role("admin","hr"))])
    def csv_export(session:Session=Depends(db)):
        items=[serialize(x,session) for x in session.scalars(select(TravelOrder).order_by(TravelOrder.id.desc()).limit(500)).all()]
        buf=StringIO();w=csv.writer(buf,delimiter=";",lineterminator="\r\n")
        w.writerow(["ID","Zamestnanec","Účel","Miesto","Začiatok","Koniec","Stav","Stravné EUR",
                    "Kilometrovné EUR","Palivo EUR","Ostatné náhrady EUR","Náhrady EUR","Preddavok EUR","Doplatok EUR"])
        for x in items:
            w.writerow([safe_csv_cell(value) for value in [
                x["id"],x["employee_name"],x["purpose"],x["destination"],x["starts_at"],
                x["ends_at"],x["status"],x["meal_allowance_eur"],x["mileage_eur"],x["fuel_eur"],
                x["expenses_eur"],x["travel_total_eur"],x["advance_eur"],x["to_pay_eur"]]])
        return StreamingResponse(iter([("\ufeff"+buf.getvalue()).encode("utf-8")]),media_type="text/csv; charset=utf-8",
            headers={"Cache-Control":"no-store","Content-Disposition":'attachment; filename="bid_sluzobne_cesty.csv"'})
    return TravelOrder,TravelMeal
