"""RFID terminal for USB readers acting as keyboard (UID + Enter).
Use a dedicated scanner, not employee credentials. Configure via environment.
"""
import json
import os
import time
import urllib.request
import urllib.error

URL = os.environ.get("ATTENDANCE_URL", "http://127.0.0.1:8000").rstrip("/")
KEY = os.environ["TERMINAL_API_KEY"]
DEVICE = os.environ.get("DEVICE_ID", "rpi-01")
def send(uid):
    data = json.dumps({"card_uid":uid,"device_id":DEVICE,"kind":"toggle"}).encode()
    req = urllib.request.Request(URL + "/api/terminal/punch",data=data,headers={"Content-Type":"application/json","X-Terminal-Key":KEY},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=8) as response:
            print(response.read().decode(),flush=True)
    except urllib.error.HTTPError as error:
        print(f"HTTP {error.code}: {error.read().decode()}",flush=True)
    except Exception as error:
        print(f"Network error: {error}",flush=True)
if __name__=="__main__":
    print(f"RFID scanner active: {DEVICE}. Scan card UID and press Enter.",flush=True)
    while True:
        try:
            uid=input().strip()
            if uid and len(uid)<=128:send(uid)
        except (EOFError,KeyboardInterrupt):break
        except Exception as error:print(error,flush=True);time.sleep(1)
