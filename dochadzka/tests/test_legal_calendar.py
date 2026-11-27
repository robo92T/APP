from datetime import date
from legal_calendar import is_workday

def test_working_holidays_2026():
    assert is_workday(date(2026,5,8))
    assert is_workday(date(2026,9,15))
    assert is_workday(date(2026,9,1))
    assert is_workday(date(2026,11,17))

def test_nonworking_public_holidays():
    assert not is_workday(date(2026,1,1))
    assert not is_workday(date(2026,12,25))

def test_weekends():
    assert not is_workday(date(2026,11,28))

def test_2027_holidays_restore():
    assert not is_workday(date(2027,9,15))
