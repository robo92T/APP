"""Encrypted portable application backups.

The API always encrypts employee data, account password hashes and RFID identifiers.
Do not upload backup files into GitHub repositories or send them by email.
"""
import base64
import json
import secrets
from datetime import date, datetime
from io import BytesIO
from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

MAGIC=b"BID-ATTENDANCE-BACKUP-1\n"
ITERATIONS=600000

class BackupRequest(BaseModel):
    passphrase:str=Field(min_length=16,max_length=512)

def derive_key(password,salt):
    return PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=ITERATIONS).derive(password.encode("utf-8"))

def seal(payload:dict,password:str)->bytes:
    salt=secrets.token_bytes(16)
    nonce=secrets.token_bytes(12)
    raw=json.dumps(payload,ensure_ascii=False,default=_json).encode("utf-8")
    cipher=AESGCM(derive_key(password,salt)).encrypt(nonce,raw,MAGIC)
    return MAGIC+salt+nonce+cipher

def unseal(data:bytes,password:str)->dict:
    if not data.startswith(MAGIC) or len(data)<len(MAGIC)+16+12+16:
        raise ValueError("Neplatný súbor zálohy")
    off=len(MAGIC)
    salt=data[off:off+16];nonce=data[off+16:off+28]
    raw=AESGCM(derive_key(password,salt)).decrypt(nonce,data[off+28:],MAGIC)
    obj=json.loads(raw)
    if obj.get("format")!="bid-attendance-v1":raise ValueError("Nepodporovaný formát zálohy")
    return obj

def _json(value):
    if isinstance(value,(datetime,date)):return value.isoformat()
    raise TypeError("Unsupported backup data type")

def snapshot(session:Session,Base)->dict:
    tables={}
    for table in Base.metadata.sorted_tables:
        rows=session.execute(select(table)).mappings().all()
        tables[table.name]=[dict(r) for r in rows]
    return {"format":"bid-attendance-v1","created_at":datetime.utcnow().isoformat(),
            "tables":tables,"table_count":len(tables),"schema_version":"1"}

def install(app,Base,db,require_role,audit):
    @app.post("/api/admin/backup",dependencies=[Depends(require_role("admin"))])
    def encrypted_backup(payload:BackupRequest,session:Session=Depends(db)):
        # Record backup action before capturing the consistent snapshot.
        audit(session,"admin","backup.export","Encrypted manual backup")
        session.commit()
        data=seal(snapshot(session,Base),payload.passphrase)
        filename="bid-dochadzka-"+datetime.utcnow().strftime("%Y%m%d-%H%M")+".bidbak"
        return StreamingResponse(iter([data]),media_type="application/octet-stream",headers={
            "Content-Disposition":f'attachment; filename="{filename}"',
            "Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
