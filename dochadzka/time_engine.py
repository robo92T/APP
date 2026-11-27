"""Pure attendance interval classification. Produces time quantities, NOT statutory premiums."""
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
import holidays
TZ=ZoneInfo("Europe/Bratislava")
UTC=timezone.utc

def normalize(dt):
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)

def attendance_intervals(events):
    """Build work intervals excluding breaks; invalid punches add explicit warnings."""
    events=sorted(events,key=lambda e:(normalize(e.at),getattr(e,"id",0)))
    intervals=[];warnings=[];working=None;active=None
    for event in events:
        at=normalize(event.at)
        kind=event.kind
        if kind=="in":
            if working is not None:
                warnings.append("Duplicitný príchod")
            else:
                working=at;active=at
        elif kind=="break_start":
            if working is None or active is None:
                warnings.append("Prestávka bez práce")
            else:
                if at>active:intervals.append((active,at))
                active=None
        elif kind=="break_end":
            if working is None or active is not None:
                warnings.append("Neplatný koniec prestávky")
            else:
                active=at
        elif kind=="out":
            if working is None:
                warnings.append("Odchod bez príchodu")
            else:
                if active is not None and at>active:intervals.append((active,at))
                working=None;active=None
    if working is not None:warnings.append("Neuzatvorený príchod")
    return intervals,warnings

def minutes(start,end):
    return max(0,int((end-start).total_seconds()//60))

def split_minutes(intervals,from_day:date,to_day:date):
    """Split by Bratislava calendar days and 22:00-06:00 local night windows."""
    holiday_dates=set(holidays.country_holidays("SK",years=range(from_day.year,to_day.year+1)))
    tally={"worked_minutes":0,"night_minutes":0,"saturday_minutes":0,
           "sunday_minutes":0,"holiday_label_minutes":0}
    day=from_day
    while day<=to_day:
        next_day=day+timedelta(days=1)
        start=datetime.combine(day,time.min,TZ).astimezone(UTC)
        finish=datetime.combine(next_day,time.min,TZ).astimezone(UTC)
        night_morning_end=datetime.combine(day,time(6),TZ).astimezone(UTC)
        night_evening_start=datetime.combine(day,time(22),TZ).astimezone(UTC)
        for ia,ib in intervals:
            a=max(ia,start);b=min(ib,finish)
            if b<=a:continue
            val=minutes(a,b)
            tally["worked_minutes"]+=val
            if day.weekday()==5:tally["saturday_minutes"]+=val
            if day.weekday()==6:tally["sunday_minutes"]+=val
            if day in holiday_dates:tally["holiday_label_minutes"]+=val
            for na,nb in ((start,night_morning_end),(night_evening_start,finish)):
                lo=max(a,na);hi=min(b,nb)
                if hi>lo:tally["night_minutes"]+=minutes(lo,hi)
        day=next_day
    return tally

def calculate(events,from_day,to_day):
    intervals,warnings=attendance_intervals(events)
    result=split_minutes(intervals,from_day,to_day)
    result["warnings"]=warnings
    result["note"]="Iba časové súčty, nie výpočet mzdových príplatkov. Sviatky 2026 a príplatky vyžadujú právne overenie."
    return result
