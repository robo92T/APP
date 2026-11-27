from datetime import datetime, date, timezone
from types import SimpleNamespace
from time_engine import calculate, attendance_intervals

def event(kind,stamp):
    return SimpleNamespace(kind=kind,at=datetime.fromisoformat(stamp),id=0)

def test_daytime_with_unpaid_break():
    events=[event("in","2026-11-27T08:00:00+01:00"),event("break_start","2026-11-27T12:00:00+01:00"),
        event("break_end","2026-11-27T12:30:00+01:00"),event("out","2026-11-27T16:30:00+01:00")]
    result=calculate(events,date(2026,11,27),date(2026,11,27))
    assert result["worked_minutes"]==480
    assert result["night_minutes"]==0

def test_night_shift_cross_midnight():
    events=[event("in","2026-11-27T22:00:00+01:00"),event("out","2026-11-28T06:00:00+01:00")]
    result=calculate(events,date(2026,11,27),date(2026,11,28))
    assert result["worked_minutes"]==480
    assert result["night_minutes"]==480
    assert result["saturday_minutes"]==360

def test_duplicate_in_does_not_double_count():
    events=[event("in","2026-11-27T08:00:00+01:00"),event("in","2026-11-27T08:05:00+01:00"),
        event("out","2026-11-27T09:00:00+01:00")]
    result=calculate(events,date(2026,11,27),date(2026,11,27))
    assert result["worked_minutes"]==60
    assert result["warnings"]
