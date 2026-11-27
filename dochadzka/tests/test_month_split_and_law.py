"""Regressions for cross-midnight work and 2026 legal calendars."""
from datetime import datetime,date
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from pdf_reports import build_rows
from legal_calendar import is_workday,is_premium_holiday
TZ=ZoneInfo("Europe/Bratislava")

def event(kind,when):
    return SimpleNamespace(kind=kind,at=datetime.fromisoformat(when),id=0)

def person():
    return SimpleNamespace(id=1,name="Ukazkovy Pracovnik",weekly_minutes=2250,
        work_days=5,start_date=date(2020,1,1),end_date=None)

def test_split_night_between_months():
    events=[event("in","2026-11-30T18:00:00+01:00"),
            event("out","2026-12-01T06:00:00+01:00")]
    shift={date(2026,11,30):{"planned_minutes":720,
        "start_time":"18:00","end_time":"06:00"}}
    november=build_rows(person(),events,shift,[],2026,11)
    december=build_rows(person(),events,shift,[],2026,12)
    assert november[-1]["worked"]==360
    assert november[-1]["plan"]==360
    assert december[0]["worked"]==360
    assert december[0]["plan"]==360

def test_break_is_not_working_time():
    events=[event("in","2026-11-02T07:30:00+01:00"),
        event("break_start","2026-11-02T11:30:00+01:00"),
        event("break_end","2026-11-02T12:00:00+01:00"),
        event("out","2026-11-02T15:30:00+01:00")]
    daily=build_rows(person(),events,{},[],2026,11)
    result=next(row for row in daily if row["day"]==date(2026,11,2))
    assert result["worked"]==450
    assert result["breaks"]==30

def test_2026_working_holidays_still_premium():
    for value in (date(2026,5,8),date(2026,9,15)):
        assert is_workday(value) is True
        assert is_premium_holiday(value) is True
    assert is_premium_holiday(date(2026,9,1)) is False
    assert is_premium_holiday(date(2026,10,28)) is False
