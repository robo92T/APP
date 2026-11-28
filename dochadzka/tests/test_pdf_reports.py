from datetime import datetime, date, timezone
from types import SimpleNamespace
from pathlib import Path
import pytest
from pdf_reports import build_rows, make_pdf, minutes_label

def test_minutes_label():
    assert minutes_label(485) == "+8:05"
    assert minutes_label(-45) == "−0:45"

def test_month_rows_and_pdf_document():
    employee=SimpleNamespace(name="Testovaci Zamestnanec",id=7,
        weekly_minutes=2250,work_days=5,start_date=date(2026,1,1),end_date=None)
    rows=build_rows(employee,[],{},[],2026,11)
    assert len(rows)==30
    assert rows[0]["day"]==date(2026,11,1)
    assert rows[-1]["day"]==date(2026,11,30)
    assert any(r["plan"] for r in rows)
    # Font path is bundled into the deployed Docker image.
    if not Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf").exists():
        pytest.skip("DejaVu font unavailable outside Docker")
    doc=make_pdf(employee,rows,2026,11)
    assert doc.read(4)==b"%PDF"
