"""Non-working Slovak public holidays. Separate statutory holiday labels from days off.
Reference: Act 241/1993 and 2026 transitional provision.
"""
from datetime import date
import holidays

REGULAR_WORKING_HOLIDAYS = {(9,1),(11,17)}
SPECIAL_WORKING_2026 = {(5,8),(9,15)}
def nonworking_holidays(year:int)->set[date]:
    days=set(holidays.country_holidays("SK",years=[year]).keys())
    for month,day in REGULAR_WORKING_HOLIDAYS:
        days.discard(date(year,month,day))
    if year==2026:
        for month,day in SPECIAL_WORKING_2026:
            days.discard(date(year,month,day))
    return days
def is_workday(day:date)->bool:
    return day.weekday()<5 and day not in nonworking_holidays(day.year)
