"""HR-only mapping of NFC/RFID identifiers; accepts a reader-provided serial number.

Web NFC supports NDEF tags on compatible Android browsers, but not every
generic MIFARE/RFID UID. USB readers in keyboard wedge mode are supported.
Tag UID is an identifier only; not a cryptographic credential.
"""
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

class AssignTag(BaseModel):
    employee_id:int=Field(gt=0)
    tag_uid:str=Field(min_length=4,max_length=128)

def install(app,Employee,db,require_role,audit):
    @app.post("/api/hr/nfc/assign",dependencies=[Depends(require_role("admin","hr"))])
    def assign(payload:AssignTag,actor=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        uid=payload.tag_uid.strip().upper()
        if len(uid)<4 or len(uid)>128:raise HTTPException(422,"Neplatný identifikátor čipu")
        if any(c not in "0123456789ABCDEF:-" for c in uid):
            raise HTTPException(422,"Použi hexadecimálny UID z čítačky RFID/NFC")
        employee=session.get(Employee,payload.employee_id)
        if employee is None:raise HTTPException(404,"Zamestnanec neexistuje")
        if not employee.active:raise HTTPException(409,"Zamestnanec nie je aktívny")
        other=session.scalar(select(Employee).where(
            Employee.card_uid==uid,Employee.id!=employee.id))
        if other:raise HTTPException(409,"Tento čip už používa iný zamestnanec")
        previous=employee.card_uid
        employee.card_uid=uid
        audit(session,actor.username,"nfc.assign",
              f"employee={employee.id};new_uid={uid};replaced={bool(previous)}")
        session.commit()
        return {"employee_id":employee.id,"name":employee.name,"assigned":True,"tag_uid":uid,
            "warning":"UID je klonovateľné; nepoužívaj samotné NFC ako autentizáciu pre vzdialené pípnutie."}
