"""Monthly attendance PDF export for administrators and HR.

A transparent attendance overview, not a payroll determination.
Employee identity is verified by privileged role; no employee access to others.
"""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from xml.sax.saxutils import escape
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
from work_rules import expected_break

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
    """Split completed work and breaks at local midnight, including month boundaries.

    Shift entries may be integer minutes, ORM Shift objects or dicts with
    planned_minutes/start_time/end_time. Entire periods containing explicit
    shifts are treated as individually scheduled; unscheduled days have zero
    fund in that mode. Payroll must review partial rosters.
    """
    first=date(year,month,1)
    last=date(year,month,monthrange(year,month)[1])
    daily_ref=employee.weekly_minutes/max(1,employee.work_days)
    rows={first+timedelta(days=n):{"ins":[],"outs":[],"minutes":0,
        "breaks":0,"warnings":[]} for n in range((last-first).days+1)}
    plan_by_day={day:0 for day in rows}
    explicit=bool(shifts)
    def normalize(at):
        return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)
    def allocate(start,end,field):
        # Split in UTC using Bratislava local midnight for daylight-saving safety.
        cursor=start
        while cursor<end:
            d=cursor.astimezone(TZ).date()
            next_midnight=datetime.combine(d+timedelta(days=1),time.min,TZ).astimezone(timezone.utc)
            limit=min(end,next_midnight)
            if d in rows:
                rows[d][field]+=max(0,int((limit-cursor).total_seconds()//60))
            cursor=limit
    for shift_day,shift in shifts.items():
        if isinstance(shift,(int,float)):
            if shift_day in plan_by_day:plan_by_day[shift_day]+=int(shift)
            continue
        def value(field):
            return shift.get(field) if isinstance(shift,dict) else getattr(shift,field)
        planned=int(value("planned_minutes"))
        start_hm=value("start_time")
        end_hm=value("end_time")
        if not start_hm or not end_hm or planned<=0:
            if shift_day in plan_by_day:plan_by_day[shift_day]+=max(0,planned)
            continue
        begin_dt=datetime.combine(shift_day,datetime.strptime(start_hm,"%H:%M").time(),TZ)
        end_dt=datetime.combine(shift_day,datetime.strptime(end_hm,"%H:%M").time(),TZ)
        if end_dt<=begin_dt:end_dt+=timedelta(days=1)
        full_minutes=max(1,int((end_dt-begin_dt).total_seconds()//60))
        cursor=begin_dt.astimezone(timezone.utc)
        stop=end_dt.astimezone(timezone.utc)
        assigned=0
        while cursor<stop:
            d=cursor.astimezone(TZ).date()
            nxt=datetime.combine(d+timedelta(days=1),time.min,TZ).astimezone(timezone.utc)
            finish=min(nxt,stop)
            piece=max(0,int((finish-cursor).total_seconds()//60))
            amount=planned-assigned if finish==stop else round(planned*piece/full_minutes)
            if d in plan_by_day:plan_by_day[d]+=amount
            assigned+=amount
            cursor=finish
    if not explicit:
        for day in plan_by_day:
            if day.weekday()<employee.work_days and is_workday(day):
                plan_by_day[day]=round(daily_ref)

    session_start=None
    pause_start=None
    pauses=[]
    for event in sorted(events,key=lambda e:(normalize(e.at),getattr(e,"id",0))):
        kind=event.kind;at=normalize(event.at)
        if kind=="void":continue
        if kind=="in":
            if session_start is not None:
                day=session_start.astimezone(TZ).date()
                if day in rows:rows[day]["warnings"].append("Dvojitý príchod")
            else:
                session_start=at;pause_start=None;pauses=[]
        elif kind=="break_start":
            if session_start is not None and pause_start is None:pause_start=at
        elif kind=="break_end":
            if pause_start is not None:
                pauses.append((pause_start,at));pause_start=None
        elif kind=="out":
            if session_start is None:continue
            if pause_start is not None:
                pauses.append((pause_start,at));pause_start=None
            work_spans=[(session_start,at)]
            for a,b in pauses:
                if b<=a:continue
                adjusted=[]
                for lo,hi in work_spans:
                    if b<=lo or a>=hi:adjusted.append((lo,hi))
                    else:
                        if lo<a:adjusted.append((lo,a))
                        if b<hi:adjusted.append((b,hi))
                work_spans=adjusted
                allocate(a,b,"breaks")
            # If no lunch break was punched, deduct the non-working
            # 30 min TPP / 60 min dispatcher break once for the completed shift.
            # Do not deduct twice if the employee used explicit break punches.
            gross_minutes=max(0,int((at-session_start).total_seconds()//60))
            explicit=sum(max(0,int((hi-lo).total_seconds()//60)) for lo,hi in pauses)
            arrival_day=session_start.astimezone(TZ).date()
            relevant_shift=shifts.get(arrival_day)
            dispatcher_like=False
            if relevant_shift is not None and not isinstance(relevant_shift,(int,float)):
                sh_start=relevant_shift.get("start_time") if isinstance(relevant_shift,dict) else getattr(relevant_shift,"start_time","")
                sh_end=relevant_shift.get("end_time") if isinstance(relevant_shift,dict) else getattr(relevant_shift,"end_time","")
                sh_plan=relevant_shift.get("planned_minutes") if isinstance(relevant_shift,dict) else getattr(relevant_shift,"planned_minutes",0)
                if (sh_start,sh_end,sh_plan) in (("06:00","18:00",660),("18:00","06:00",660)):
                    dispatcher_like=True
            regime="dispatcher" if dispatcher_like else getattr(employee,"work_regime","fixed")
            automatic=expected_break(regime,session_start,at,explicit_break=explicit)
            if automatic:
                total_span=max(0,int((at-session_start).total_seconds()//60))
                midpoint=session_start+timedelta(minutes=total_span//2)
                b_start=midpoint-timedelta(minutes=automatic//2)
                b_end=b_start+timedelta(minutes=automatic)
                next_spans=[]
                for lo,hi in work_spans:
                    if b_end<=lo or b_start>=hi:next_spans.append((lo,hi))
                    else:
                        if lo<b_start:next_spans.append((lo,b_start))
                        if b_end<hi:next_spans.append((b_end,hi))
                work_spans=next_spans
                allocate(b_start,b_end,"breaks")
            for lo,hi in work_spans:
                if hi>lo:allocate(lo,hi,"minutes")
            arrival_day=session_start.astimezone(TZ).date()
            leave_day=at.astimezone(TZ).date()
            if arrival_day in rows:rows[arrival_day]["ins"].append(session_start)
            if leave_day in rows:rows[leave_day]["outs"].append(at)
            session_start=None;pauses=[]
    if session_start is not None:
        day=session_start.astimezone(TZ).date()
        if day in rows:rows[day]["warnings"].append("Neuzatvorený príchod")
    credited_kinds={"vacation","doctor","accompany","paid_leave","wedding",
        "funeral","blood_donation","training","business_trip"}
    output=[]
    for day,rec in rows.items():
        applicable=employee.start_date<=day and (employee.end_date is None or day<=employee.end_date)
        plan=plan_by_day[day] if applicable else 0
        categories=[];credit=0
        for absence in absences:
            if absence.start<=day<=absence.end:
                categories.append(absence.kind)
                if absence.kind in credited_kinds:
                    credit+=absence.minutes if absence.minutes is not None and absence.start==absence.end else plan
        # Approved full-day home office is an administratively credited 8h workday:
        # no synthetic in/out punches, no device location, no second punch required.
        # Scheduled fund is the ceiling for saldo so a 7.5h contract doesn't acquire
        # artificial overtime from the fixed 8h home-office attendance display.
        home_office = "home_office" in categories
        auto_home_office = 0
        if home_office and applicable and plan>0:
            if rec["minutes"] == 0:
                auto_home_office = 480
            else:
                rec["warnings"].append("Home office sa prekrýva so skutočným pípnutím – automatických 8 h sa nepripočíta")
        elif home_office and applicable:
            rec["warnings"].append("Home office je schválený na deň bez plánovanej práce – automatické hodiny treba overiť")
        recorded_work=rec["minutes"]+auto_home_office
        requested_credit=min(credit,plan)
        if requested_credit and recorded_work:
            rec["warnings"].append("Prekryv práce a plateného voľna – over, či nejde o duplicitné hodiny")
        # Never double-count work, approved home office and paid leave.
        credit=min(requested_credit,max(0,plan-recorded_work))
        # The 8h automatic HO entry is a full-day credit, not approved overtime.
        saldo=(min(recorded_work,plan) if auto_home_office else recorded_work)+credit-plan
        first_in=rec["ins"][0] if rec["ins"] else None
        last_out=rec["outs"][-1] if rec["outs"] else None
        output.append({"day":day,"in":first_in,"out":last_out,
            "worked":recorded_work,"home_office_auto_minutes":auto_home_office,
            "breaks":rec["breaks"],"plan":plan,"credit":credit,
            "saldo":saldo,
            "absence":", ".join(sorted(set(categories))),"warnings":rec["warnings"]})
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
    person=f"{escape(employee.name)} · ID {employee.id}"
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
            minutes_label(r["saldo"]),Paragraph(escape(annotation or "—"),tiny)])
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

def install(app,Employee,Event,Absence,db,require_role,current_account):
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
        shift_rows=session.execute(text("SELECT day, planned_minutes, start_time, end_time FROM shift WHERE employee_id=:id AND day>=:first AND day<=:last"),{"id":employee_id,"first":(begin-timedelta(days=1)).isoformat(),"last":end.isoformat()}).all()
        shifts={date.fromisoformat(str(row[0])):{"planned_minutes":int(row[1]),"start_time":row[2],"end_time":row[3]} for row in shift_rows}
        rows=build_rows(employee,events,shifts,absences,year,month)
        pdf=make_pdf(employee,rows,year,month)
        filename=f"dochadzka_{employee_id}_{year}_{month:02d}.pdf"
        return StreamingResponse(pdf,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="{filename}"',"Cache-Control":"no-store"})

    @app.get("/api/me/monthly-pdf")
    def my_monthly_pdf(year:int=Query(ge=2020,le=2100),month:int=Query(ge=1,le=12),account=Depends(current_account),session:Session=Depends(db)):
        """An employee may download only their own attendance report."""
        if account.employee_id is None:
            raise HTTPException(403,"Účet nie je priradený zamestnancovi")
        return monthly_pdf(employee_id=account.employee_id,year=year,month=month,session=session)
