"""Restore a previously encrypted BID attendance backup to a fresh database.

LOCAL / TRUSTED ADMINISTRATOR ONLY. Stop the web service before running.
Usage: DATABASE_URL="postgresql://..." python restore_backup.py backup.bidbak
Never pass the decryption passphrase in shell arguments, URLs or Git.
"""
import argparse
import getpass
import sys
from datetime import datetime, date
from sqlalchemy import delete, insert, select, text, Date, DateTime, Boolean
from main import Base, engine, Employee, Event, Absence
from secure_backup import unseal

def convert(table,row):
    result={}
    for col in table.columns:
        if col.name not in row:continue
        value=row[col.name]
        if value is not None and isinstance(col.type,DateTime):
            value=datetime.fromisoformat(value)
        elif value is not None and isinstance(col.type,Date):
            value=date.fromisoformat(value)
        result[col.name]=value
    return result

def restore(source,password,confirmation):
    if confirmation!="RESTORE INTO EMPTY DATABASE":
        raise RuntimeError("Explicit restore confirmation required")
    payload=unseal(source,password)
    expected={table.name for table in Base.metadata.sorted_tables}
    if set(payload.get("tables",{}))!=expected:
        raise RuntimeError("The schema differs from this backup. No changes were made.")
    with engine.begin() as conn:
        # Never replace live attendance: only a fresh DB with a bootstrap admin is allowed.
        for table_name in ("employee","event","absence","shift","employee_profile","month_close"):
            t=Base.metadata.tables.get(table_name)
            if t is not None and conn.scalar(select(t).limit(1)) is not None:
                raise RuntimeError("Target database contains real data. Refusing destructive restore.")
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(delete(table))
        for table in Base.metadata.sorted_tables:
            rows=payload["tables"][table.name]
            if rows:
                conn.execute(insert(table),[convert(table,row) for row in rows])
        if engine.dialect.name=="postgresql":
            # Explicit primary keys require sequence alignment.
            for table in Base.metadata.sorted_tables:
                if "id" not in table.c:continue
                table_name=table.name
                seq=conn.scalar(text("SELECT pg_get_serial_sequence(:table,:column)"),{"table":table_name,"column":"id"})
                if seq:
                    value=conn.scalar(select(text("COALESCE(MAX(id), 0)")).select_from(table))
                    conn.execute(text("SELECT setval(CAST(:seq AS regclass), :value, :called)"),
                                 {"seq":seq,"value":max(1,int(value or 0)),"called":bool(value)})
    return {"tables":len(expected),"format":payload["format"]}

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("backup")
    args=parser.parse_args()
    print("WARNING: This tool restores all attendance records and accounts. Use only a NEW database.")
    phrase=input("To continue, type RESTORE INTO EMPTY DATABASE: ")
    password=getpass.getpass("Backup passphrase: ")
    try:
        with open(args.backup,"rb") as f:raw=f.read()
        result=restore(raw,password,phrase)
        print("Restore complete:",result)
    except Exception as exc:
        print("Restore FAILED:",str(exc),file=sys.stderr)
        sys.exit(1)
