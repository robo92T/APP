"""Non-working Slovak public holidays. Separate statutory holiday labels from days off.
Reference: Act 241/1993 and 2026 transitional provision.
"""
from datetime import date
import holidays

REGULAR_WORKING_HOLIDAYS = {(9,1),(10,28),(11,17)}
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

# Statutory status and remuneration status are two separate axes.
# 2026-05-08 and 2026-09-15: working days but remain premium holidays.
# Source: National Labour Inspectorate, 2026 published guidance.
def is_premium_holiday(day:date)->bool:
    """Reference flag for working-time categorization; not a wage calculation."""
    if (day.month,day.day) in REGULAR_WORKING_HOLIDAYS:
        return False
    if day.year==2026 and (day.month,day.day) in SPECIAL_WORKING_2026:
        return True
    return day in holidays.country_holidays("SK",years=[day.year])

def holiday_details(day:date)->dict:
    all_holidays=holidays.country_holidays("SK",years=[day.year])
    label=all_holidays.get(day)
    if day.year==2026:
        label=label or {(5,8):"Deň víťazstva nad fašizmom",(9,15):"Sedembolestná Panna Mária"}.get((day.month,day.day))
    return {
        "date":day.isoformat(),
        "name":label,
        "is_holiday_label":label is not None,
        "is_day_off":day in nonworking_holidays(day.year),
        "premium_reference":is_premium_holiday(day),
        "requires_payroll_confirmation":True,
    }
