"""Container startup: ensure mounted SQLite disk is writable, then drop privileges."""
import os
import pwd

uid = pwd.getpwnam("app").pw_uid
gid = pwd.getpwnam("app").pw_gid
path = os.path.abspath(os.environ.get("BID_DB", "/app/data/dochadzka.db"))
directory = os.path.dirname(path)
os.makedirs(directory, exist_ok=True)
if os.geteuid() == 0:
    os.chown(directory, uid, gid)
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)

os.execvp("uvicorn", [
    "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port",
    os.environ.get("PORT", "8000"), "--proxy-headers", "--forwarded-allow-ips", "*"
])
