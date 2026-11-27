"""Optional scheduled encrypted backup to a private, independently managed S3 bucket.

Never store employee data in GitHub. Requires persistent DB and explicitly
configured backup bucket, encryption passphrase, and IAM credentials.
Schedules are best-effort while web worker runs; production should use an
external cron and provider-managed point-in-time database recovery.
"""
import asyncio
import hashlib
import os
import threading
from datetime import datetime, date, timezone

from fastapi import Depends, HTTPException
from sqlalchemy import DateTime, Integer, String, Text, select, func
from sqlalchemy.orm import Mapped, mapped_column, Session

from secure_backup import snapshot, seal, unseal

_LOCK=threading.Lock()

def now():return datetime.now(timezone.utc)

def install(app,Base,engine,db,require_role,audit,persistent):
    class BackupRun(Base):
        __tablename__="backup_run"
        id:Mapped[int]=mapped_column(primary_key=True)
        started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
        finished_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=True)
        status:Mapped[str]=mapped_column(String(20),default="running")
        object_key:Mapped[str]=mapped_column(String(300),default="")
        size_bytes:Mapped[int]=mapped_column(Integer,default=0)
        error:Mapped[str]=mapped_column(Text,default="")
    Base.metadata.create_all(engine)

    def configured():
        return bool(
            persistent and not str(engine.url).startswith("sqlite") and
            os.getenv("BACKUP_S3_BUCKET") and
            os.getenv("BACKUP_ENCRYPTION_PASSPHRASE") and
            len(os.getenv("BACKUP_ENCRYPTION_PASSPHRASE",""))>=24 and
            os.getenv("AWS_REGION")
        )
    def run_backup():
        if not configured():
            return {"status":"disabled","message":"Vyžaduje trvalý PostgreSQL a súkromné zálohovacie S3 úložisko."}
        if not _LOCK.acquire(blocking=False):
            return {"status":"busy"}
        run_id=None
        try:
            with Session(engine) as session:
                entry=BackupRun(status="running")
                session.add(entry);session.commit();run_id=entry.id
            with Session(engine) as session:
                payload=seal(snapshot(session,Base),os.environ["BACKUP_ENCRYPTION_PASSPHRASE"])
            import boto3
            bucket=os.environ["BACKUP_S3_BUCKET"]
            region=os.environ["AWS_REGION"]
            key="bid-dochadzka/encrypted/"+now().strftime("%Y/%m/%d/") + now().strftime("%Y%m%dT%H%M%SZ")+".bidbak"
            client=boto3.client("s3",region_name=region)
            digest=hashlib.sha256(payload).hexdigest()
            client.put_object(Bucket=bucket,Key=key,Body=payload,
                              ContentType="application/octet-stream",
                              ServerSideEncryption="AES256",
                              Metadata={"sha256":digest,"format":"bid-attendance-v1"})
            # Verify uploaded ciphertext and authenticated decryption, not just HTTP status.
            response=client.get_object(Bucket=bucket,Key=key)
            returned=response["Body"].read()
            if hashlib.sha256(returned).hexdigest()!=digest:
                raise RuntimeError("Backup integrity verification failed")
            check=unseal(returned,os.environ["BACKUP_ENCRYPTION_PASSPHRASE"])
            if check.get("format")!="bid-attendance-v1":raise RuntimeError("Invalid backup format")
            with Session(engine) as session:
                entry=session.get(BackupRun,run_id)
                entry.status="verified";entry.finished_at=now()
                entry.object_key=key;entry.size_bytes=len(payload)
                audit(session,"system","backup.verified",f"backup_id={run_id};bytes={len(payload)}")
                session.commit()
            return {"status":"verified","backup_id":run_id,"bytes":len(payload),
                    "stored_in":"private S3 bucket","recovery_tested":False}
        except Exception as exc:
            with Session(engine) as session:
                if run_id is not None:
                    entry=session.get(BackupRun,run_id)
                    if entry:
                        entry.status="failed";entry.finished_at=now()
                        # Never store cloud credentials, URL or secret in application DB.
                        entry.error=type(exc).__name__+": záloha alebo kontrola integrity zlyhala"
                        session.commit()
            return {"status":"failed","error":"Záloha alebo kontrola integrity zlyhala"}
        finally:
            _LOCK.release()

    async def daily_loop():
        await asyncio.sleep(90)
        while True:
            if configured():
                with Session(engine) as session:
                    last=session.scalar(select(BackupRun).where(
                        BackupRun.status=="verified").order_by(BackupRun.finished_at.desc()).limit(1))
                    last_day=last.finished_at.date() if last and last.finished_at else None
                if last_day!=date.today():
                    try:await asyncio.to_thread(run_backup)
                    except Exception:pass
            await asyncio.sleep(60*60)

    if os.getenv("BACKUP_SCHEDULER_ENABLED","false").lower()=="true":
        @app.on_event("startup")
        async def start_scheduled_backup():
            app.state.backup_task=asyncio.create_task(daily_loop())
        @app.on_event("shutdown")
        async def stop_scheduled_backup():
            task=getattr(app.state,"backup_task",None)
            if task:
                task.cancel()
                try:await task
                except asyncio.CancelledError:pass

    @app.get("/api/admin/backups/status",dependencies=[Depends(require_role("admin"))])
    def backup_status(session:Session=Depends(db)):
        runs=session.scalars(select(BackupRun).order_by(BackupRun.id.desc()).limit(12)).all()
        return {
            "configured":configured(),
            "persistent_database":persistent,
            "destination":"Private S3" if os.getenv("BACKUP_S3_BUCKET") else "Nepripojené",
            "scheduler_enabled":os.getenv("BACKUP_SCHEDULER_ENABLED","false").lower()=="true",
            "note":"Webový plán Free sa môže uspať. Pre spoľahlivosť je nutný platený PostgreSQL s obnovou a externý plánovač.",
            "runs":[{"id":r.id,"started_at":r.started_at,"finished_at":r.finished_at,
                "status":r.status,"size_bytes":r.size_bytes,"error":r.error} for r in runs]
        }

    @app.post("/api/admin/backups/run",dependencies=[Depends(require_role("admin"))])
    def manual_backup(actor=Depends(require_role("admin")),session:Session=Depends(db)):
        result=run_backup()
        audit(session,actor.username,"backup.manual.run",result["status"])
        session.commit()
        if result["status"]=="disabled":raise HTTPException(503,result["message"])
        if result["status"]=="failed":raise HTTPException(502,result["error"])
        return result
