"""Official Slovak legislation watcher with explicit human-controlled rule updates.

The monitor NEVER executes code from external pages or alters payroll rules
automatically. Source changes create notices, not legal conclusions.
"""
import asyncio
import difflib
import hashlib
import os
import re
import threading
from datetime import datetime, date, timezone
from typing import Optional, Literal
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, select, func
from sqlalchemy.orm import Mapped, mapped_column, Session

SOURCES = {
    "zakonnik_prace": {
        "title": "Zákonník práce – 311/2001 Z. z.",
        "url": "https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2001/311/",
        "authority": "Slov-Lex", "topic": "Pracovný čas, dovolenka, prekážky a mzda"
    },
    "sviatky": {
        "title": "Sviatky a dni pracovného pokoja – 241/1993 Z. z.",
        "url": "https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/1993/241/",
        "authority": "Slov-Lex", "topic": "Kalendár a sviatočné zvýhodnenie"
    },
    "nip_pracovny_cas": {
        "title": "NIP – Pracovný čas a doba odpočinku",
        "url": "https://www.ip.gov.sk/pracovnopravne-vztahy/pracovny-cas-doba-odpocinku/",
        "authority": "Národný inšpektorát práce", "topic": "Usmernenia a aktuality"
    },
    "nip_prekazky": {
        "title": "NIP – Novinky v prekážkach od 1. januára 2026",
        "url": "https://www.ip.gov.sk/pracovnopravne-vztahy/pracovny-cas-doba-odpocinku/novinky-prekazkach-praci-od-1-januara-2026.html",
        "authority": "Národný inšpektorát práce", "topic": "Lekár a sprevádzanie"
    },
    "cestovne_nahrady": {
        "title":"Zákon o cestovných náhradách – 283/2002 Z. z.",
        "url":"https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2002/283/",
        "authority":"Slov-Lex","topic":"Služobné cesty, stravné a náhrady"
    },
    "sadzby_stravne_2026": {
        "title":"Sadzby stravného od 1.12.2026 – 255/2026 Z. z.",
        "url":"https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2026/255/",
        "authority":"Slov-Lex","topic":"Tuzemské stravné a minimálna poukážka"
    },
    "nip_stravne_2026": {
        "title":"NIP – sumy stravného od 1.12.2026",
        "url":"https://www.ip.gov.sk/pracovnopravne-vztahy/pracovne-cesty/sumy-stravneho-od-1-decembra-2026.html",
        "authority":"Národný inšpektorát práce","topic":"Tuzemské stravné"
    },
    "kilometrove_2026": {
        "title":"NIP – kilometrovné 2026",
        "url":"https://www.ip.gov.sk/pracovnopravne-vztahy/pracovne-cesty/sumy-zakladnej-nahrady-za-pouzivanie-motorovych-vozidiel-pri-pracovnych-cestach-od-1-januara-2026-2.html",
        "authority":"Národný inšpektorát práce","topic":"Náhrady za súkromné vozidlo"
    },
    "nip_sviatky": {
        "title": "NIP – Sviatky 8. máj a 15. september 2026",
        "url": "https://www.ip.gov.sk/pracovnopravne-vztahy/pracovny-cas-doba-odpocinku/sviatky-8-maj-15-september-2026-z-pohladu-pracovneho-prava.html",
        "authority": "Národný inšpektorát práce", "topic": "Osobitné sviatky roka 2026"
    }
}
ALLOWED_HOSTS={"www.slov-lex.sk","slov-lex.sk","static.slov-lex.sk","www.ip.gov.sk","ip.gov.sk"}
RULES={
    "doctor_paid_days": {"label":"Lekár – referenčný počet platených dní za rok","min":0,"max":30,"default":7},
    "escort_paid_days": {"label":"Sprevádzanie – základný referenčný počet dní","min":0,"max":30,"default":7},
    "escort_extra_days_max": {"label":"Sprevádzanie – maximálny osobitný dodatočný nárok","min":0,"max":30,"default":7},
}
_lock=threading.Lock()

def utcnow(): return datetime.now(timezone.utc)

def normalize_html(html:str)->str:
    """Extract readable official-source text, ignoring scripts, navigation and banners."""
    soup=BeautifulSoup(html,"html.parser")
    for tag in soup(["script","style","noscript","nav","footer","header","form","svg"]):
        tag.decompose()
    root=soup.select_one("article") or soup.select_one("main") or soup.select_one("#content") or soup.body or soup
    content=root.get_text(" ",strip=True)
    return re.sub(r"\s+"," ",content).strip()[:250000]

def fetch_official(source):
    url=source["url"]
    if urlparse(url).hostname not in ALLOWED_HOSTS: raise ValueError("Nepovolená doména")
    with httpx.Client(timeout=18,follow_redirects=True,
                      headers={"User-Agent":"BID-Dockadzka-LegalMonitor/1.0 (official-public-sources-only)",
                               "Accept":"text/html"}) as client:
        response=client.get(url)
        response.raise_for_status()
        if response.url.scheme!="https" or response.url.host not in ALLOWED_HOSTS:
            raise ValueError("Nepovolené presmerovanie")
        if "html" not in response.headers.get("content-type","").lower():
            raise ValueError("Nepodporovaný typ obsahu")
        if len(response.content)>4_000_000: raise ValueError("Príliš veľký zdroj")
        text=normalize_html(response.text)
        if len(text)<150: raise ValueError("Oficiálna stránka nevrátila dostatočný text")
        return text

def excerpt_difference(old:str,new:str)->str:
    """Only store a bounded, informational text difference. No legal inference."""
    matcher=difflib.SequenceMatcher(None,old[:12000],new[:12000],autojunk=False)
    changes=[]
    for operation,i1,i2,j1,j2 in matcher.get_opcodes():
        if operation=="equal":continue
        before=old[max(0,i1-80):min(len(old),i2+80)]
        after=new[max(0,j1-80):min(len(new),j2+80)]
        changes.append(f"{operation.upper()}\nPREDTÝM: {before[:360]}\nTERAZ: {after[:360]}")
        if len(changes)>=4:break
    return "\n\n".join(changes)[:2400] or "Stránka sa zmenila, zobrazený výňatok neobsahuje podrobný rozdiel."

def install(app,Base,engine,db,require_role,audit):
    class SourceState(Base):
        __tablename__="legal_monitor_source"
        key:Mapped[str]=mapped_column(String(60),primary_key=True)
        fingerprint:Mapped[Optional[str]]=mapped_column(String(64),nullable=True)
        excerpt:Mapped[str]=mapped_column(Text,default="")
        checked_at:Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)
        changed_at:Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)
        error:Mapped[str]=mapped_column(String(400),default="")
        checks:Mapped[int]=mapped_column(Integer,default=0)

    class Notice(Base):
        __tablename__="legal_monitor_notice"
        id:Mapped[int]=mapped_column(primary_key=True)
        source_key:Mapped[str]=mapped_column(ForeignKey("legal_monitor_source.key"),index=True)
        before_hash:Mapped[str]=mapped_column(String(64))
        after_hash:Mapped[str]=mapped_column(String(64))
        summary:Mapped[str]=mapped_column(Text)
        detected_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
        status:Mapped[str]=mapped_column(String(18),default="new")  # new, reviewed, dismissed
        reviewed_by:Mapped[Optional[str]]=mapped_column(String(80),nullable=True)
        reviewed_at:Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)

    class RuleVersion(Base):
        __tablename__="legal_rule_version"
        id:Mapped[int]=mapped_column(primary_key=True)
        key:Mapped[str]=mapped_column(String(70),index=True)
        value:Mapped[int]=mapped_column(Integer)
        effective_date:Mapped[date]=mapped_column(Date)
        source_notice_id:Mapped[Optional[int]]=mapped_column(ForeignKey("legal_monitor_notice.id"),nullable=True)
        approved_by:Mapped[str]=mapped_column(String(80))
        approved_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
        reason:Mapped[str]=mapped_column(Text)

    class Proposal(Base):
        __tablename__="legal_rule_proposal"
        id:Mapped[int]=mapped_column(primary_key=True)
        key:Mapped[str]=mapped_column(String(70))
        proposed_value:Mapped[int]=mapped_column(Integer)
        effective_date:Mapped[date]=mapped_column(Date)
        notice_id:Mapped[int]=mapped_column(ForeignKey("legal_monitor_notice.id"))
        rationale:Mapped[str]=mapped_column(Text)
        status:Mapped[str]=mapped_column(String(20),default="pending")
        created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
        created_by:Mapped[str]=mapped_column(String(80))
        decided_by:Mapped[Optional[str]]=mapped_column(String(80),nullable=True)
        decided_at:Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True),nullable=True)

    Base.metadata.create_all(engine)

    class ProposalCreate(BaseModel):
        notice_id:int=Field(gt=0)
        rule_key:str
        new_value:int
        effective_date:date
        rationale:str=Field(min_length=20,max_length=1500)

    class Decision(BaseModel):
        justification:str=Field(min_length=12,max_length=1000)

    def effective_rules(session:Session,at:date):
        result={}
        for key,rule in RULES.items():
            versions=session.scalars(select(RuleVersion).where(
                RuleVersion.key==key,RuleVersion.effective_date<=at
            ).order_by(RuleVersion.effective_date.desc(),RuleVersion.id.desc()).limit(1)).all()
            result[key]=versions[0].value if versions else rule["default"]
        return result

    def check_once():
        if not _lock.acquire(blocking=False):
            return {"status":"busy","checked":0,"changes":0,"errors":[]}
        count=0;changes=0;errors=[]
        try:
            for key,source in SOURCES.items():
                try:content=fetch_official(source)
                except Exception as exc:
                    errors.append({"source":key,"error":str(exc)[:280]})
                    with Session(engine) as session:
                        state=session.get(SourceState,key)
                        if state is None:state=SourceState(key=key);session.add(state)
                        state.checked_at=utcnow();state.error=str(exc)[:380]
                        state.checks=(state.checks or 0)+1
                        session.commit()
                    continue
                new_hash=hashlib.sha256(content.encode("utf-8")).hexdigest()
                with Session(engine) as session:
                    state=session.get(SourceState,key)
                    if state is None:state=SourceState(key=key);session.add(state)
                    old_hash=state.fingerprint
                    if old_hash and old_hash!=new_hash:
                        summary=excerpt_difference(state.excerpt,content)
                        session.add(Notice(source_key=key,before_hash=old_hash,after_hash=new_hash,summary=summary))
                        state.changed_at=utcnow();changes+=1
                    state.fingerprint=new_hash
                    state.excerpt=content[:12000]
                    state.checked_at=utcnow()
                    state.error=""
                    state.checks=(state.checks or 0)+1
                    session.commit()
                    count+=1
            return {"status":"complete","checked":count,"changes":changes,"errors":errors,
                "disclaimer":"Zistená zmena stránky nie je automaticky zmenou právneho predpisu."}
        finally:_lock.release()

    async def monitor_loop():
        # Render Free web services can sleep, so this is best-effort only.
        await asyncio.sleep(45)
        while True:
            try:await asyncio.to_thread(check_once)
            except Exception:
                # A failed check is visible in source statuses after manual retry.
                pass
            await asyncio.sleep(12*60*60)

    if os.getenv("LEGAL_MONITOR_ENABLED","true").lower()=="true":
        @app.on_event("startup")
        async def start_legal_monitor():
            app.state.legal_monitor_task=asyncio.create_task(monitor_loop())
        @app.on_event("shutdown")
        async def stop_legal_monitor():
            task=getattr(app.state,"legal_monitor_task",None)
            if task:
                task.cancel()
                try:await task
                except asyncio.CancelledError:pass

    @app.get("/api/legal-monitor/status",dependencies=[Depends(require_role("admin","hr"))])
    def status(session:Session=Depends(db)):
        states={s.key:s for s in session.scalars(select(SourceState)).all()}
        pending=session.scalar(select(func.count(Notice.id)).where(Notice.status=="new")) or 0
        data=[]
        for key,source in SOURCES.items():
            state=states.get(key)
            data.append({**source,"key":key,"baseline_set":bool(state and state.fingerprint),
                "checked_at":state.checked_at if state else None,
                "changed_at":state.changed_at if state else None,
                "error":state.error if state else "",
                "checks":state.checks if state else 0})
        return {"sources":data,"new_notices":pending,
                "automatic_checks":"best-effort every 12 hours while Render service runs",
                "automatic_rule_updates":False,
                "note":"Zmena obsahu je len podnet na právnu kontrolu; dátum účinnosti sa automaticky neodhaduje."}

    @app.post("/api/legal-monitor/check",dependencies=[Depends(require_role("admin"))])
    def manual_check(actor=Depends(require_role("admin")),session:Session=Depends(db)):
        result=check_once()
        audit(session,actor.username,"legal.monitor.check",
              f"sources={result['checked']};changes={result['changes']}")
        session.commit()
        return result

    @app.get("/api/legal-monitor/notices",dependencies=[Depends(require_role("admin","hr"))])
    def notices(session:Session=Depends(db)):
        result=[]
        for n in session.scalars(select(Notice).order_by(Notice.id.desc()).limit(100)).all():
            source=SOURCES.get(n.source_key,{})
            result.append({"id":n.id,"title":source.get("title",n.source_key),
                "url":source.get("url",""),"authority":source.get("authority",""),
                "topic":source.get("topic",""),"detected_at":n.detected_at,
                "summary":n.summary,"before_hash":n.before_hash,
                "after_hash":n.after_hash,"status":n.status,
                "reviewed_by":n.reviewed_by,"reviewed_at":n.reviewed_at})
        return result

    @app.post("/api/legal-monitor/notices/{notice_id}/review",dependencies=[Depends(require_role("admin","hr"))])
    def review(notice_id:int,actor=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        n=session.get(Notice,notice_id)
        if not n:raise HTTPException(404,"Upozornenie neexistuje")
        n.status="reviewed";n.reviewed_by=actor.username;n.reviewed_at=utcnow()
        audit(session,actor.username,"legal.notice.review",str(notice_id))
        session.commit();return {"id":n.id,"status":n.status}

    @app.get("/api/legal-monitor/rules",dependencies=[Depends(require_role("admin","hr"))])
    def rules(session:Session=Depends(db)):
        current=effective_rules(session,date.today())
        return [{"key":key,**rule,"active_value":current[key]} for key,rule in RULES.items()]

    @app.get("/api/legal-monitor/proposals",dependencies=[Depends(require_role("admin","hr"))])
    def proposals(session:Session=Depends(db)):
        result=[]
        for p in session.scalars(select(Proposal).order_by(Proposal.id.desc()).limit(100)).all():
            result.append({"id":p.id,"key":p.key,"proposed_value":p.proposed_value,
                "effective_date":p.effective_date,"notice_id":p.notice_id,
                "rationale":p.rationale,"status":p.status,"created_by":p.created_by,
                "decided_by":p.decided_by,"created_at":p.created_at,"decided_at":p.decided_at})
        return result

    @app.post("/api/legal-monitor/proposals",dependencies=[Depends(require_role("admin","hr"))],status_code=201)
    def create_proposal(payload:ProposalCreate,actor=Depends(require_role("admin","hr")),
                        session:Session=Depends(db)):
        rule=RULES.get(payload.rule_key)
        if rule is None:raise HTTPException(422,"Nepodporované pravidlo")
        if not rule["min"]<=payload.new_value<=rule["max"]:
            raise HTTPException(422,"Nová hodnota je mimo povoleného rozsahu")
        notice=session.get(Notice,payload.notice_id)
        if not notice:raise HTTPException(422,"Zvoľ zaznamenanú oficiálnu zmenu")
        p=Proposal(key=payload.rule_key,notice_id=payload.notice_id,
                   proposed_value=payload.new_value,effective_date=payload.effective_date,
                   rationale=payload.rationale,created_by=actor.username)
        session.add(p);session.flush()
        audit(session,actor.username,"legal.proposal.create",str(p.id))
        session.commit();return {"id":p.id,"status":"pending"}

    @app.post("/api/legal-monitor/proposals/{proposal_id}/approve",dependencies=[Depends(require_role("admin"))])
    def approve(proposal_id:int,decision:Decision,actor=Depends(require_role("admin")),
                session:Session=Depends(db)):
        p=session.get(Proposal,proposal_id)
        if not p:raise HTTPException(404,"Návrh neexistuje")
        if p.status!="pending":raise HTTPException(409,"Návrh už bol vybavený")
        if p.key not in RULES:raise HTTPException(422,"Nepodporované pravidlo")
        p.status="approved";p.decided_by=actor.username;p.decided_at=utcnow()
        v=RuleVersion(key=p.key,value=p.proposed_value,
            effective_date=p.effective_date,source_notice_id=p.notice_id,
            approved_by=actor.username,reason=p.rationale+" | SCHVÁLENIE: "+decision.justification)
        session.add(v)
        audit(session,actor.username,"legal.rule.approved",
              f"{p.key}={p.proposed_value};effective={p.effective_date};proposal={p.id}")
        session.commit()
        return {"id":p.id,"status":"approved","key":p.key,"value":p.proposed_value,
                "effective_date":p.effective_date}

    @app.post("/api/legal-monitor/proposals/{proposal_id}/reject",dependencies=[Depends(require_role("admin"))])
    def reject(proposal_id:int,decision:Decision,actor=Depends(require_role("admin")),
               session:Session=Depends(db)):
        p=session.get(Proposal,proposal_id)
        if not p:raise HTTPException(404,"Návrh neexistuje")
        if p.status!="pending":raise HTTPException(409,"Návrh už bol vybavený")
        p.status="rejected";p.decided_by=actor.username;p.decided_at=utcnow()
        audit(session,actor.username,"legal.proposal.rejected",
              f"{p.id}: {decision.justification[:200]}")
        session.commit();return {"id":p.id,"status":"rejected"}

    @app.get("/api/legal-monitor/history",dependencies=[Depends(require_role("admin","hr"))])
    def history(session:Session=Depends(db)):
        versions=session.scalars(select(RuleVersion).order_by(RuleVersion.id.desc()).limit(150)).all()
        return [{"id":v.id,"key":v.key,"value":v.value,
                 "effective_date":v.effective_date,"approved_by":v.approved_by,
                 "approved_at":v.approved_at,"reason":v.reason,
                 "source_notice_id":v.source_notice_id} for v in versions]

    @app.post("/api/legal-monitor/history/{version_id}/rollback",dependencies=[Depends(require_role("admin"))])
    def rollback(version_id:int,decision:Decision,actor=Depends(require_role("admin")),
                 session:Session=Depends(db)):
        """Audit a new compensating rule version; never delete history."""
        target=session.get(RuleVersion,version_id)
        if not target:raise HTTPException(404,"Historické pravidlo neexistuje")
        newest=session.scalar(select(RuleVersion).where(RuleVersion.key==target.key)
                              .order_by(RuleVersion.effective_date.desc(),RuleVersion.id.desc()).limit(1))
        if not newest or newest.id!=version_id:
            raise HTTPException(409,"Zmeniť späť možno iba najnovšiu verziu pravidla")
        previous=session.scalar(select(RuleVersion).where(
            RuleVersion.key==target.key,RuleVersion.id<target.id
        ).order_by(RuleVersion.effective_date.desc(),RuleVersion.id.desc()).limit(1))
        old_value=previous.value if previous is not None else RULES[target.key]["default"]
        new=RuleVersion(key=target.key,value=old_value,effective_date=date.today(),
            source_notice_id=target.source_notice_id,approved_by=actor.username,
            reason=f"ROLLBACK verzie {version_id}: "+decision.justification)
        session.add(new);session.flush()
        audit(session,actor.username,"legal.rule.rollback",
              f"{target.key}:{target.value}->{old_value};version={target.id};new={new.id}")
        session.commit()
        return {"rolled_back_version":version_id,"new_version":new.id,
                "key":target.key,"restored_value":old_value,"effective_date":new.effective_date}

    # Exposed to calculation modules as a controlled DB reader, not a mutable global.
    return effective_rules
