"""Monthly attendance PDF export for administrators and HR.

A transparent attendance overview, not a payroll determination.
Employee identity is verified by privileged role; no employee access to others.
"""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo
from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from legal_calendar import is_workday

TZ=ZoneInfo("Europe/Bratislava")
FONT_PATH="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD_PATH="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def register_fonts():
    try:
        pdfmetrics.getFont("SK-Regular")
    except KeyError:
        pdfmetrics.registerFont(TTFont("SK-Regular",FONT_PATH))
        pdfmetrics.registerFont(TTFont("SK-Bold",BOLD_PATH))

def time_label(dt):
    return dt.astimezone(TZ).strftime("%H:%M") if dt else "—"

def minutes_label(value):
    v=int(value)
    sign="−" if v<0 else "+" if v>0 else ""
    return f"{sign}{abs(v)//60}:{abs(v)%60:02d}"

def build_rows(employee,events,shifts,absences,year,month):
    """Daily events are matched sequentially, with overnight punches credited to arrival day."""
    first=date(year,month,1)
    last=date(year,month,monthrange(year,month)[1])
    daily_ref=employee.weekly_minutes/max(1,employee.work_days)
    rows={first+timedelta(days=n):{"ins":[],"outs":[],"minutes":0,"breaks":0,"warnings":[]} for n in range((last-first).days+1)}
    state=None
    pause=None
    pause_minutes=0
    for event in events:
        at=event.at.replace(tzinfo=timezone.utc) if event.at.tzinfo is None else event.at.astimezone(timezone.utc)
        kind=event.kind
        if kind=="in":
            if state is not None:
                day=state.astimezone(TZ).date()
                if day in rows:rows[day]["warnings"].append("Dvojitý príchod")
            else:
                state=at;pause=None;pause_minutes=0
        elif kind=="break_start":
            if state is not None and pause is None:pause=at
        elif kind=="break_end":
            if pause is not None:
                pause_minutes+=max(0,int((at-pause).total_seconds()//60));pause=None
        elif kind=="out":
            if state is None:continue
            day=state.astimezone(TZ).date()
            if pause is not None:
                pause_minutes+=max(0,int((at-pause).total_seconds()//60))
            if day in rows:
                worked=max(0,int((at-state).total_seconds()//60)-pause_minutes)
                rows[day]["ins"].append(state)
                rows[day]["outs"].append(at)
                rows[day]["minutes"]+=worked
                rows[day]["breaks"]+=pause_minutes
            state=None;pause=None;pause_minutes=0
    if state is not None:
        day=state.astimezone(TZ).date()
        if day in rows:rows[day]["warnings"].append("Neuzavretý príchod")
    credited_kinds={"vacation","doctor","accompany","paid_leave","wedding","funeral","blood_donation","training","business_trip"}
    output=[]
    for day,rec in rows.items():
        applicable= employee.start_date<=day and (employee.end_date is None or day<=employee.end_date)
        shift=shifts.get(day)
        plan=(shift if shift is not None else round(daily_ref) if day.weekday()<employee.work_days and is_workday(day) else 0) if applicable else 0
        categories=[]
        credit=0
        for a in absences:
            if a.start<=day<=a.end:
                categories.append(a.kind)
                if a.kind in credited_kinds:
                    credit+=a.minutes if a.minutes is not None and a.start==a.end else plan
        credit=min(credit,plan)
        if credit and rec["minutes"]:rec["warnings"].append("Prekryv práce a voľna")
        first_in=rec["ins"][0] if rec["ins"] else None
        last_out=rec["outs"][-1] if rec["outs"] else None
        output.append({"day":day,"in":first_in,"out":last_out,
            "worked":rec["minutes"],"breaks":rec["breaks"],"plan":plan,"credit":credit,
            "saldo":rec["minutes"]+credit-plan,"absence":", ".join(sorted(set(categories))),"warnings":rec["warnings"]})
    return output

def make_pdf(employee,rows,year,month):
    register_fonts()
    buffer=BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=landscape(A4),rightMargin=13*mm,leftMargin=13*mm,topMargin=13*mm,bottomMargin=15*mm,title="Mesačný výkaz dochádzky")
    navy=colors.HexColor("#15345C")
    muted=colors.HexColor("#62728A")
    pale=colors.HexColor("#EAF0F8")
    base=ParagraphStyle("base",fontName="SK-Regular",fontSize=8,leading=12,textColor=navy)
    small=ParagraphStyle("small",parent=base,fontSize=7,leading=10)
    tiny=ParagraphStyle("tiny",parent=base,fontSize=6,leading=9)
    white_header=ParagraphStyle("white_header",parent=small,fontName="SK-Bold",textColor=colors.white)
    title=ParagraphStyle("title",parent=base,fontName="SK-Bold",fontSize=19,leading=24)
    right=ParagraphStyle("right",parent=base,alignment=TA_RIGHT)
    story=[]
    story.append(Paragraph("MESAČNÝ VÝKAZ DOCHÁDZKY",title))
    story.append(Spacer(1,3*mm))
    person=f"{employee.name} · ID {employee.id}"
    summary=Table([[Paragraph("<b>Zamestnanec:</b> "+person,base),
        Paragraph("<b>Obdobie:</b> "+f"{month:02d}/{year}",base),
        Paragraph("<b>Týždenný fond:</b> "+minutes_label(employee.weekly_minutes),base)]],
        colWidths=[110*mm,56*mm,95*mm])
    summary.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),pale),("BOX",(0,0),(-1,-1),0.4,colors.HexColor("#D4E0EF")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9)]))
    story.append(summary);story.append(Spacer(1,5*mm))
    total={k:sum(r[k] for r in rows) for k in ("worked","breaks","plan","credit","saldo")}
    overview=Table([[Paragraph("<b>Fond</b><br/>"+minutes_label(total["plan"]),base),
        Paragraph("<b>Odpracované</b><br/>"+minutes_label(total["worked"]),base),
        Paragraph("<b>Prestávky</b><br/>"+minutes_label(total["breaks"]),base),
        Paragraph("<b>Započítané voľno</b><br/>"+minutes_label(total["credit"]),base),
        Paragraph("<b>Orientačné saldo</b><br/>"+minutes_label(total["saldo"]),base)]],
        colWidths=[52*mm]*5)
    overview.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F6F8FC")),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#DCE4EF")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10)]))
    story.append(overview);story.append(Spacer(1,5*mm))
    header=["Deň","Príchod","Odchod","Práca","Prestávka","Fond","Voľno","Saldo","Druh neprítomnosti / poznámka"]
    data=[[Paragraph(h,white_header) for h in header]]
    for r in rows:
        day=r["day"]
        annotation=", ".join(filter(None,[r["absence"],*r["warnings"]]))
        data.append([day.strftime("%d.%m.")+" "+["Po","Ut","St","Št","Pi","So","Ne"][day.weekday()],
            time_label(r["in"]),time_label(r["out"]),minutes_label(r["worked"]),
            minutes_label(r["breaks"]),minutes_label(r["plan"]),minutes_label(r["credit"]),
            minutes_label(r["saldo"]),Paragraph(annotation or "—",tiny)])
    t=Table(data,repeatRows=1,colWidths=[24*mm,21*mm,21*mm,22*mm,24*mm,21*mm,21*mm,22*mm,65*mm],hAlign="LEFT")
    commands=[("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),
      ("FONTNAME",(0,0),(-1,0),"SK-Bold"),("FONTNAME",(0,1),(-1,-1),"SK-Regular"),
      ("FONTSIZE",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,0),9),
      ("TOPPADDING",(0,0),(-1,0),9),("TOPPADDING",(0,1),(-1,-1),4),
      ("BOTTOMPADDING",(0,1),(-1,-1),4),("LINEBELOW",(0,1),(-1,-1),.3,colors.HexColor("#E5EBF2")),("VALIGN",(0,0),(-1,-1),"MIDDLE")]
    for n,r in enumerate(rows,1):
        if r["day"].weekday()>=5:commands.append(("BACKGROUND",(0,n),(-1,n),colors.HexColor("#F6F8FA")))
    t.setStyle(TableStyle(commands));story.append(t)
    story.append(Spacer(1,4*mm))
    story.append(Paragraph("<b>UPOZORNENIE:</b> Výkaz je informatívny, nie mzdový list. Fond, započítanie prekážok, saldo a cezpolnočné smeny vyžadujú overenie rozvrhu a schválenie mzdárom. Príplatky, nadčasy a zákonné nároky nie sú týmto výkazom stanovené.",small))
    generated=datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
    story.append(Paragraph("Vygenerované: "+generated+" · SK Dochádzka",tiny))
    def footer(canvas,document):
        canvas.saveState()
        canvas.setFont("SK-Regular",7)
        canvas.setFillColor(muted)
        canvas.drawString(13*mm,9*mm,"SK Dochádzka · interný pracovný výkaz")
        canvas.drawRightString(284*mm,9*mm,f"Strana {document.page}")
        canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    buffer.seek(0)
    return buffer

def install(app,Employee,Event,Absence,db,require_role):
    @app.get("/api/reports/monthly/{employee_id}/pdf",dependencies=[Depends(require_role("admin","hr"))])
    def monthly_pdf(employee_id:int,year:int=Query(ge=2020,le=2100),month:int=Query(ge=1,le=12),session:Session=Depends(db)):
        employee=session.get(Employee,employee_id)
        if not employee:raise HTTPException(404,"Zamestnanec neexistuje")
        begin=date(year,month,1); end=date(year,month,monthrange(year,month)[1])
        # Include one day beyond month boundaries to match overnight shifts; only IN in month is reported.
        from_utc=datetime.combine(begin-timedelta(days=1),time.min,TZ).astimezone(timezone.utc)
        to_utc=datetime.combine(end+timedelta(days=2),time.min,TZ).astimezone(timezone.utc)
        events=session.scalars(select(Event).where(Event.employee_id==employee_id,Event.at>=from_utc,Event.at<to_utc).order_by(Event.at,Event.id)).all()
        absences=session.scalars(select(Absence).where(Absence.employee_id==employee_id,Absence.status=="approved",Absence.start<=end,Absence.end>=begin)).all()
        shift_rows=session.execute(text("SELECT day, planned_minutes FROM shift WHERE employee_id=:id AND day>=:first AND day<=:last"),{"id":employee_id,"first":begin.isoformat(),"last":end.isoformat()}).all()
        shifts={date.fromisoformat(str(row[0])):int(row[1]) for row in shift_rows}
        rows=build_rows(employee,events,shifts,absences,year,month)
        pdf=make_pdf(employee,rows,year,month)
        filename=f"dochadzka_{employee_id}_{year}_{month:02d}.pdf"
        return StreamingResponse(pdf,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="{filename}"',"Cache-Control":"no-store"})
