"""BID shift profiles and unpunched breaks: conservative, auditable calculation helpers.

An unpunched statutory meal break is automatically subtracted only on
completed shifts longer than six gross hours and only when no explicit
break events are recorded. Dispatcher's 60-minute break is BID POLICY,
not a statutory minimum. Exceptions for uninterruptible work require HR.
"""
from datetime import datetime,time,timedelta
from decimal import Decimal,ROUND_HALF_UP
from zoneinfo import ZoneInfo
TZ=ZoneInfo("Europe/Bratislava")
SHIFT_PRESETS={
    "tpp":{"label":"TPP · 8 h čistá práca + 30 min prestávka",
        "start_time":"08:00","end_time":"16:30","planned_minutes":480,
        "break_minutes":30},
    "dispatch_day":{"label":"Dispečer · denná (11 h + 1 h prestávka)",
        "start_time":"06:00","end_time":"18:00","planned_minutes":660,
        "break_minutes":60},
    "dispatch_night":{"label":"Dispečer · nočná (11 h + 1 h prestávka)",
        "start_time":"18:00","end_time":"06:00","planned_minutes":660,
        "break_minutes":60},
    "dispatch_half":{"label":"Dispečer · polzmena (6 h)",
        "start_time":"06:00","end_time":"12:00","planned_minutes":360,
        "break_minutes":0},
    "dispatch_off":{"label":"Dispečer · voľno",
        "start_time":"00:00","end_time":"00:00","planned_minutes":0,
        "break_minutes":0},
    "agreement":{"label":"Dohoda · dohodnutý čas podľa rozpisu",
        "start_time":"08:00","end_time":"12:00","planned_minutes":240,
        "break_minutes":0},
}
def break_policy(regime, gross_minutes, explicit_break_minutes):
    if gross_minutes<=360 or explicit_break_minutes>0:return 0
    return 60 if regime in ("dispatcher","dispatch","dispecer") else 30

def expected_break(regime,start,end,explicit_break=0):
    return break_policy(regime,max(0,int((end-start).total_seconds()//60)),explicit_break)

def schedule_span_minutes(start_time,end_time):
    start=datetime.strptime(start_time,"%H:%M")
    finish=datetime.strptime(end_time,"%H:%M")
    if finish<=start:finish+=timedelta(days=1)
    return int((finish-start).total_seconds()//60)

def premium_amount(minutes,hourly_rate):
    return (Decimal(minutes)*Decimal(str(hourly_rate))/Decimal(60)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)

def classify_agreement(kind,weekly_minutes):
    if kind=="agreement_activity" and weekly_minutes>600:
        return "Dohoda o pracovnej činnosti má obvykle najviac 10 h týždenne."
    if kind=="agreement_student" and weekly_minutes>1200:
        return "Brigádnická práca študentov sa posudzuje podľa priemeru najviac 20 h týždenne."
    if kind=="agreement_seasonal" and weekly_minutes>2400:
        return "Sezónna dohoda o pracovnej činnosti môže mať priemer najviac 40 h týždenne; over 4-mesačný priemer a 520 h/rok."
    if kind=="agreement_task":return "Dohoda o vykonaní práce: sleduj 350 h za kalendárny rok."
    return None
