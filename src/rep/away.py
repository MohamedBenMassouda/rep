import datetime

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEKDAY_PREFIX_LENGTH = 3
DAYS_IN_WEEK = 7
HOURS_IN_DAY = 24
DAY_TODAY = "today"
DAY_TOMORROW = "tomorrow"
HOME = "home"
NO_AWAY_DAYS = "none"
WEEKLY_SEPARATOR = ","
DAY_FORMAT = "%a %d %b"
HOUR_FORMAT = "{hour}:00"


def weekday_named(text):
    name = text.strip().lower()

    if len(name) < WEEKDAY_PREFIX_LENGTH:
        return None

    return next((weekday for weekday in WEEKDAYS if weekday.startswith(name)), None)


def away_hour(text):
    return int(text) if text.isdigit() and int(text) < HOURS_IN_DAY else None


def away_day(text, today):
    name = text.strip().lower()

    if name == DAY_TODAY:
        return today

    if name == DAY_TOMORROW:
        return today + datetime.timedelta(days=1)

    weekday = weekday_named(name)

    if weekday:
        return today + datetime.timedelta(days=(WEEKDAYS.index(weekday) - today.weekday()) % DAYS_IN_WEEK)

    try:
        day = datetime.date.fromisoformat(name)
    except ValueError:
        return None

    return day if day >= today else None


def weekly_away(text):
    if text.strip().lower() == NO_AWAY_DAYS:
        return {}

    days = {}

    for part in text.split(WEEKLY_SEPARATOR):
        words = part.split()

        if len(words) != 2 or not weekday_named(words[0]) or away_hour(words[1]) is None:
            return None

        days[weekday_named(words[0])] = away_hour(words[1])

    return days


def weekly_away_text(weekly):
    return f"{WEEKLY_SEPARATOR} ".join(f"{weekday[:WEEKDAY_PREFIX_LENGTH]} {hour}" for weekday, hour in weekly.items()) \
        or NO_AWAY_DAYS


def end_hour_on(day, schedule, away_days):
    if day.isoformat() in away_days:
        hour = away_days[day.isoformat()]
    else:
        hour = schedule["away"].get(WEEKDAYS[day.weekday()])

    return schedule["end_hour"] if hour is None else min(hour, schedule["end_hour"])


def upcoming_away(away_days, today):
    return {day: hour for day, hour in away_days.items() if day >= today.isoformat()}


def day_text(day):
    return day.strftime(DAY_FORMAT)


def hour_text(hour):
    return HOUR_FORMAT.format(hour=hour)


def away_plan_lines(schedule, away_days, today):
    lines = [f"Every {weekday.capitalize()}: challenges until {hour_text(min(hour, schedule['end_hour']))}"
             for weekday, hour in schedule["away"].items()]

    for day, hour in sorted(upcoming_away(away_days, today).items()):
        end_hour = end_hour_on(datetime.date.fromisoformat(day), schedule, away_days)
        place = "Home" if hour is None else "Out"
        lines.append(f"{place} on {day_text(datetime.date.fromisoformat(day))}: challenges until {hour_text(end_hour)}")

    return lines or [f"No away days: challenges until {hour_text(schedule['end_hour'])} every day."]
