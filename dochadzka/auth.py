"""Authentication for attendance backend.
Set AUTH_SECRET to a random 64+ character value in production.
Legacy X-Admin-Key endpoints are kept for development; disable them in production.
"""
import base64, hashlib, hmac, os, secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, Header, HTTPException, Request
from jose import jwt, JWTError
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, ForeignKey, String, select
from sqlalchemy.orm import Mapped, mapped_column, Session

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=256)

class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12, max_length=256)

def make_hash(password: str) -> str:
    salt = os.urandom(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,600_000)
    return "pbkdf2_sha256$600000$"+base64.b64encode(salt).decode()+"$"+base64.b64encode(digest).decode()

def verify_password(password:str,stored:str)->bool:
    try:
        algorithm,rounds,salt,digest=stored.split("$")
        if algorithm!="pbkdf2_sha256":return False
        computed=hashlib.pbkdf2_hmac("sha256",password.encode(),base64.b64decode(salt),int(rounds))
        return hmac.compare_digest(computed,base64.b64decode(digest))
    except (ValueError,TypeError):return False

def install(app, Base, Employee, engine, db, audit):
    class Account(Base):
        __tablename__="account"
        id:Mapped[int]=mapped_column(primary_key=True)
        username:Mapped[str]=mapped_column(String(80),unique=True,index=True)
        password_hash:Mapped[str]=mapped_column(String(350))
        role:Mapped[str]=mapped_column(String(30),default="employee")
        employee_id:Mapped[Optional[int]]=mapped_column(ForeignKey("employee.id"),nullable=True)
        active:Mapped[bool]=mapped_column(Boolean,default=True)
    class PasswordPolicy(Base):
        __tablename__="password_policy"
        account_id:Mapped[int]=mapped_column(ForeignKey("account.id"),primary_key=True)
        must_change:Mapped[bool]=mapped_column(Boolean,default=True)
    Base.metadata.create_all(engine)
    # First-run bootstrap, only when explicitly configured by deployer.
    bootstrap_user=os.getenv("BOOTSTRAP_ADMIN_USERNAME","").strip()
    bootstrap_password=os.getenv("BOOTSTRAP_ADMIN_PASSWORD","")
    if bootstrap_user and len(bootstrap_password)>=12:
        with Session(engine) as session:
            if session.scalar(select(Account).limit(1)) is None:
                session.add(Account(username=bootstrap_user,password_hash=make_hash(bootstrap_password),role="admin"))
                session.commit()
            elif os.getenv("ONE_TIME_ADMIN_RESET") == "true":
                target = session.scalar(select(Account).where(Account.username == bootstrap_user, Account.role == "admin"))
                if target:
                    target.password_hash = make_hash(bootstrap_password)
                    audit(session, "system", "admin.password.reset", "operator initiated")
                    session.commit()
    secret=os.getenv("AUTH_SECRET","")
    def current(request:Request,session:Session=Depends(db)):
        bearer=request.headers.get("Authorization","")
        if not bearer.startswith("Bearer "):raise HTTPException(401,"Vyžaduje sa prihlásenie")
        if len(secret)<32:raise HTTPException(503,"AUTH_SECRET nie je bezpečne nakonfigurovaný")
        try:
            token=jwt.decode(bearer[7:],secret,algorithms=["HS256"],options={"require_exp":True,"require_sub":True})
            account=session.get(Account,int(token["sub"]))
            if not account or not account.active:raise HTTPException(401,"Neplatný účet")
            policy=session.get(PasswordPolicy,account.id)
            if policy and policy.must_change and request.url.path not in ("/api/auth/me","/api/auth/password"):
                raise HTTPException(403,"Najprv zmeň dočasné heslo")
            return account
        except (JWTError,ValueError,KeyError):raise HTTPException(401,"Neplatné prihlásenie")
    def require_role(*roles):
        def check(account=Depends(current)):
            if account.role not in roles:raise HTTPException(403,"Nedostatočné oprávnenie")
            return account
        return check
    @app.post("/api/auth/login")
    def login(payload:Credentials,session:Session=Depends(db)):
        account=session.scalar(select(Account).where(Account.username==payload.username))
        if not account or not account.active or not verify_password(payload.password,account.password_hash):
            raise HTTPException(401,"Nesprávne prihlasovacie údaje")
        if len(secret)<32:raise HTTPException(503,"AUTH_SECRET nie je nakonfigurovaný")
        issued=datetime.now(timezone.utc)
        signed=jwt.encode({"sub":str(account.id),"iat":issued,"exp":issued+timedelta(hours=8)},secret,algorithm="HS256")
        audit(session,account.username,"login","successful");session.commit()
        policy=session.get(PasswordPolicy,account.id)
        return {"access_token":signed,"token_type":"bearer","role":account.role,"username":account.username,"employee_id":account.employee_id,"must_change_password":bool(policy and policy.must_change)}
    @app.get("/api/auth/me")
    def me(account=Depends(current),session:Session=Depends(db)):
        policy=session.get(PasswordPolicy,account.id)
        return {"username":account.username,"role":account.role,"employee_id":account.employee_id,"must_change_password":bool(policy and policy.must_change)}
    @app.post("/api/auth/password")
    def change_password(payload:PasswordChange,account=Depends(current),session:Session=Depends(db)):
        if not verify_password(payload.old_password,account.password_hash):raise HTTPException(401,"Nesprávne aktuálne heslo")
        account.password_hash=make_hash(payload.new_password)
        policy=session.get(PasswordPolicy,account.id)
        if policy:policy.must_change=False
        audit(session,account.username,"password.change","self");session.commit()
        return {"success":True}
    @app.post("/api/auth/accounts")
    def create_account(payload:Credentials,role:str="employee",employee_id:Optional[int]=None,account=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        if role not in {"admin","hr","manager","employee","auditor"}:raise HTTPException(400,"Neplatná rola")
        if role=="admin" and account.role!="admin":raise HTTPException(403,"Rolu admin smie prideľovať len admin")
        if session.scalar(select(Account).where(Account.username==payload.username)):raise HTTPException(409,"Používateľ existuje")
        if employee_id and not session.get(Employee,employee_id):raise HTTPException(404,"Zamestnanec neexistuje")
        user=Account(username=payload.username,password_hash=make_hash(payload.password),role=role,employee_id=employee_id)
        session.add(user);session.flush()
        session.add(PasswordPolicy(account_id=user.id,must_change=True))
        audit(session,account.username,"account.create",payload.username);session.commit()
        return {"success":True}
    @app.post("/api/auth/employees/{employee_id}/reset-password")
    def reset_employee_password(employee_id:int,operator=Depends(require_role("admin","hr")),session:Session=Depends(db)):
        """Return a random one-time temporary password to authorized HR only."""
        target=session.scalar(select(Account).where(Account.employee_id==employee_id))
        if not target:raise HTTPException(404,"Zamestnanec nemá používateľský účet")
        if target.role=="admin" and operator.role!="admin":raise HTTPException(403,"Admin heslo smie resetovať len admin")
        temporary=secrets.token_urlsafe(18)
        target.password_hash=make_hash(temporary)
        policy=session.get(PasswordPolicy,target.id)
        if not policy:
            policy=PasswordPolicy(account_id=target.id,must_change=True)
            session.add(policy)
        else:policy.must_change=True
        audit(session,operator.username,"password.reset",target.username)
        session.commit()
        return {"username":target.username,"temporary_password":temporary,"must_change_password":True}
    return Account,current,require_role
