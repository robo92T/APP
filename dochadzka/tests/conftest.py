"""Guarantee isolated, fictitious test data regardless of runner environment."""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TEST_DIR=Path(tempfile.mkdtemp(prefix="bid-attendance-tests-"))
atexit.register(shutil.rmtree,_TEST_DIR,ignore_errors=True)
os.environ["DATABASE_URL"]="sqlite:///"+str(_TEST_DIR/"test_attendance.sqlite3")
os.environ["APP_ENV"]="preview"
os.environ["DEMO_SEED"]="10"
os.environ["AUTH_SECRET"]="unit-test-only-not-a-real-secret-long-2026"
os.environ["BOOTSTRAP_ADMIN_USERNAME"]="ci-admin"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"]="TestOnlyPassword2026!"
os.environ["ONE_TIME_ADMIN_RESET"]="false"
os.environ["DEMO_EMPLOYEE_PASSWORD"]="TestDemoEmployeeOnly2026!"
os.environ["LEGAL_MONITOR_ENABLED"]="false"
os.environ["BACKUP_SCHEDULER_ENABLED"]="false"
