"""Configurable payroll exports: CSV (UTF-8/CP1250), XLSX, JSON, XML.

An export records quantities and absence codes. It does NOT calculate wages.
User-defined fields are selected from a strict whitelist and no formulas are
accepted from untrusted employee data. Designed to be mapped to payroll imports.
"""
from calendar import monthrange
from datetime import date,datetime,time,timedelta,timezone
from io import BytesIO,StringIO
import csv,json,xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
import xlsxwriter
from fastapi import Depends,HTTPException,Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,Field
from sqlalchemy import ForeignKey,Integer,String,select
from sqlalchemy.orm import Mapped,mapped_column,Session
from time_engine import calculate
TZ=ZoneInfo("Europe/Bratislava")
FIELDS={
 "month":["personal_number","full_name","month","fond_min","worked_min","credited_min",
          "saldo_min","night_min","saturday_min","sunday_min","holiday_min","vacation_min",
          "doctor_min","accompany_min","ocr_calendar_days","warnings"],
 "day":["personal_number","full_name","day","first_in","last_out","planned_min","worked_min",
        "credited_min","saldo_min","absence","warnings"],
 "absence":["personal_number","full_name","kind","start","end","minutes","status","month"]
}
DEFAULTS=[
 ("Mesačný súhrn CSV (UTF-8)","csv","month","utf-8",";",FIELDS["month"]),
 ("Mzdový import CSV (Windows-1250)","csv","month","cp1250",";",FIELDS["month"]),
 ("Kontrolný denný výkaz Excel","xlsx","day","utf-8",";",FIELDS["day"]),
 ("Mesačný súhrn Excel","xlsx","month","utf-8",";",FIELDS["month"]),
 ("Mesačné údaje JSON","json","month","utf-8",";",FIELDS["month"]),
 ("Výmena údajov XML","xml","month","utf-8",";",FIELDS["month"]),
 ("Neprítomnosti CSV","csv","absence","utf-8",";",FIELDS["absence"])
]
class ProfileInput(BaseModel):
    name:str=Field(min_length=3,max_length=140)
    file_format:str=Field(pattern="^(csv|xlsx|json|xml)$")
    level:str=Field(pattern="^(month|day|absence)$")
    encoding:str=Field(default="utf-8",pattern="^(utf-8|cp1250)$")
    delimiter:str=Field(default=";",pattern="^(;|,|\\t)$")
    columns:list[str]=Field(min_length=1,max_length=40)

def install(app,Base,Employee,Event,Absence,Shift,engine,db,require_role,audit,build_rows):
    class ExportProfile(Base):
        __tablename__="export_profile"
        id:Mapped[int]=mapped_column(primary_key=True)
        name:Mapped[str]=mapped_column(String(140),unique=True)
        file_format:Mapped[str]=mapped_column(String(12))
        level:Mapped[str]=mapped_column(String(15))
        encoding:Mapped[str]=mapped_column(String(20),default="utf-8")
        delimiter:Mapped[str]=mapped_column(String(3),default=";")
        columns_json:Mapped[str]=mapped_column(String(2000))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        if not session.scalar(select(ExportProfile.id).limit(1)):
            for name,fmt,level,encoding,sep,columns in DEFAULTS:
                session.add(ExportProfile(name=name,file_format=fmt,level=level,encoding=encoding,
                                          delimiter=sep,columns_json=json.dumps(columns)))
            session.commit()
    def serial(item):
        return {"id":item.id,"name":item.name,"format":item.file_format,"level":item.level,
                "encoding":item.encoding,"delimiter":item.delimiter,"columns":json.loads(item.columns_json)}
    @app.get("/api/exports/profiles",dependencies=[Depends(require_role("admin","hr"))])
    def profiles(session:Session=Depends(db)):
        return [serial(x) for x in session.scalars(select(ExportProfile).order_by(ExportProfile.id)).all()]

    @app.post("/api/exports/profiles",dependencies=[Depends(require_role("admin","hr"))])
    def create_profile(payload:ProfileInput,actor=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        if not set(payload.columns).issubset(set(FIELDS[payload.level])):
            raise HTTPException(422,"Niektoré polia nie sú dostupné pre zvolenú úroveň")
        if session.scalar(select(ExportProfile).where(ExportProfile.name==payload.name)):
            raise HTTPException(409,"Profil už existuje")
        item=ExportProfile(name=payload.name,file_format=payload.file_format,level=payload.level,
                           encoding=payload.encoding,delimiter=payload.delimiter,
                           columns_json=json.dumps(payload.columns))
        session.add(item);session.flush()
        audit(session,actor.username,"exports.profile.create",str(item.id));session.commit()
        return serial(item)

    def collect(session,year,month,level):
        start=date(year,month,1)
        end=date(year,month,monthrange(year,month)[1])
        minutc=datetime.combine(start-timedelta(days=1),time.min,TZ).astimezone(timezone.utc)
        maxutc=datetime.combine(end+timedelta(days=2),time.min,TZ).astimezone(timezone.utc)
        profiles_table=Base.metadata.tables.get("employee_profile")
        personal_map={}
        if profiles_table is not None:
            for personal_id,personal_no in session.execute(
                select(profiles_table.c.employee_id,profiles_table.c.personal_number)
            ).all():
                personal_map[personal_id]=personal_no
        output=[]
        for emp in session.scalars(select(Employee).order_by(Employee.name)).all():
            punch=session.scalars(select(Event).where(Event.employee_id==emp.id,
                Event.at>=minutc,Event.at<maxutc).order_by(Event.at,Event.id)).all()
            absences=session.scalars(select(Absence).where(Absence.employee_id==emp.id,
                Absence.start<=end,Absence.end>=start)).all()
            shifts={x.day:x for x in session.scalars(select(Shift).where(
                Shift.employee_id==emp.id,Shift.day>=start-timedelta(days=1),Shift.day<=end)).all()}
            approved=[a for a in absences if a.status=="approved"]
            daily=build_rows(emp,punch,shifts,approved,year,month)
            num=personal_map.get(emp.id,str(emp.id))
            if level=="day":
                for row in daily:
                    output.append({"personal_number":num,"full_name":emp.name,
                        "day":row["day"].isoformat(),
                        "first_in":row["in"].astimezone(TZ).strftime("%H:%M") if row["in"] else "",
                        "last_out":row["out"].astimezone(TZ).strftime("%H:%M") if row["out"] else "",
                        "planned_min":row["plan"],"worked_min":row["worked"],
                        "credited_min":row["credit"],"saldo_min":row["saldo"],
                        "absence":row["absence"],"warnings":"; ".join(row["warnings"])})
            elif level=="absence":
                for a in absences:
                    output.append({"personal_number":num,"full_name":emp.name,
                        "kind":a.kind,"start":a.start.isoformat(),"end":a.end.isoformat(),
                        "minutes":a.minutes or 0,"status":a.status,"month":f"{year}-{month:02d}"})
            else:
                category=calculate(punch,start,end)
                by_kind={}
                for a in approved:
                    if a.kind not in by_kind:by_kind[a.kind]=0
                    if a.minutes is not None and a.start==a.end:
                        by_kind[a.kind]+=a.minutes
                    else:
                        by_kind[a.kind]+=sum(r["plan"] for r in daily if a.start<=r["day"]<=a.end)
                totals={key:sum(row[key] for row in daily) for key in ("plan","worked","credit","saldo")}
                output.append({"personal_number":num,"full_name":emp.name,"month":f"{year}-{month:02d}",
                    "fond_min":totals["plan"],"worked_min":totals["worked"],
                    "credited_min":totals["credit"],"saldo_min":totals["saldo"],
                    "night_min":category["night_minutes"],
                    "saturday_min":category["saturday_minutes"],"sunday_min":category["sunday_minutes"],
                    "holiday_min":category["holiday_label_minutes"],
                    "vacation_min":by_kind.get("vacation",0),"doctor_min":by_kind.get("doctor",0),
                    "accompany_min":by_kind.get("accompany",0),
                    "ocr_calendar_days":sum((min(a.end,end)-max(a.start,start)).days+1
                        for a in approved if a.kind=="ocr"),
                    "warnings":sum(len(r["warnings"]) for r in daily)+len(category["warnings"])})
        return output

    @app.get("/api/exports/download/{profile_id}",dependencies=[Depends(require_role("admin","hr"))])
    def export(profile_id:int,year:int=Query(ge=2020,le=2100),month:int=Query(ge=1,le=12),
               actor=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        item=session.get(ExportProfile,profile_id)
        if not item:raise HTTPException(404,"Exportný profil neexistuje")
        columns=json.loads(item.columns_json)
        rows=collect(session,year,month,item.level)
        filename=f"bid_mzdy_{year}_{month:02d}_{profile_id}.{item.file_format}"
        content_type="application/octet-stream"
        if item.file_format=="csv":
            output=StringIO()
            writer=csv.writer(output,delimiter=item.delimiter,lineterminator="\r\n")
            writer.writerow(columns)
            for record in rows:
                # Prefix any spreadsheet-formula-like employee string with apostrophe.
                writer.writerow(["'"+str(record.get(col,"")) if isinstance(record.get(col),str) and
                    record[col].startswith(("=","+","-","@")) else record.get(col,"") for col in columns])
            payload=output.getvalue().encode(item.encoding,errors="replace")
            content_type="text/csv; charset="+item.encoding
        elif item.file_format=="json":
            payload=json.dumps({"year":year,"month":month,"fields":columns,
                "records":[{k:row.get(k) for k in columns} for row in rows]},
                ensure_ascii=False).encode("utf-8")
            content_type="application/json"
        elif item.file_format=="xml":
            root=ET.Element("bidAttendance",{"year":str(year),"month":str(month),"version":"1"})
            for row in rows:
                el=ET.SubElement(root,"record")
                for col in columns:
                    child=ET.SubElement(el,col)
                    child.text=str(row.get(col,""))
            payload=ET.tostring(root,encoding="utf-8",xml_declaration=True)
            content_type="application/xml"
        else:
            buf=BytesIO();book=xlsxwriter.Workbook(buf,{"in_memory":True,"strings_to_formulas":False,"strings_to_urls":False})
            sheet=book.add_worksheet("Dochádzka")
            head=book.add_format({"bold":True,"font_color":"white","bg_color":"#13365F",
                                  "align":"center","text_wrap":True,"bottom":2,"bottom_color":"#F5C400"})
            integer=book.add_format({"num_format":"0","align":"right"})
            normal=book.add_format({"text_wrap":False})
            for col_index,name in enumerate(columns):sheet.write_string(0,col_index,name,head)
            for row_index,row in enumerate(rows,1):
                for col_index,name in enumerate(columns):
                    value=row.get(name,"")
                    if isinstance(value,(int,float)):sheet.write_number(row_index,col_index,value,integer)
                    else:sheet.write_string(row_index,col_index,str(value),normal)
            sheet.freeze_panes(1,0);sheet.set_row(0,32)
            sheet.set_column(0,len(columns)-1,19)
            sheet.autofilter(0,0,max(1,len(rows)),max(0,len(columns)-1))
            book.close();payload=buf.getvalue()
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        audit(session,actor.username,"exports.download",f"{profile_id}:{year}-{month:02d}")
        session.commit()
        return StreamingResponse(iter([payload]),media_type=content_type,headers={
            "Content-Disposition":f'attachment; filename="{filename}"',
            "Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
