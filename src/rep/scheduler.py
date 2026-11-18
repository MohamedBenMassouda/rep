import datetime
from dataclasses import dataclass

from rep.away import end_hour_on
from rep.progression import choose_challenge
from rep.store import EVENT_TEST

ACTION_NUDGE = "nudge"
ACTION_SUMMARY = "summary"
ACTION_RETEST = "retest"
ACTION_SCHEDULE_FIRST = "schedule_first"
ACTION_REMIND = "remind"
ACTION_CHALLENGE = "challenge"
NUDGE_KINDS = ("protein", "bedtime")
STAMP_RETEST = "retest_reminder"
STAMP_SUMMARY = "summary"
DISABLED_TIME = "off"
SECONDS_PER_MINUTE = 60


@dataclass(frozen=True)
class Decision:
    action: str
    detail: object = None


def clock_time_reached(now, clock_time):
    if clock_time == DISABLED_TIME:
        return False

    hours, minutes = (int(part) for part in clock_time.split(":"))

    return (now.hour, now.minute) >= (hours, minutes)


def stamped_today(state, stamp, today):
    return state["stamps"].get(stamp) == today.isoformat()


def last_test_day(events):
    test_days = [event["day"] for event in events if event["type"] == EVENT_TEST]

    return datetime.date.fromisoformat(max(test_days)) if test_days else None


def retest_due(state, events, today, retest_days):
    stored_day = state.get("last_test_day")
    last_test = datetime.date.fromisoformat(stored_day) if stored_day else last_test_day(events)

    return last_test is None or (today - last_test).days >= retest_days


def within_active_hours(now, schedule, away_days):
    return schedule["start_hour"] <= now.hour < end_hour_on(now.date(), schedule, away_days)


def decide(now, state, config, pack, events, busy_reason, chooser):
    today = now.date()
    nudges, schedule = config["nudges"], config["schedule"]

    if now.timestamp() < state["paused_until"]:
        return None

    for kind in NUDGE_KINDS:

        if clock_time_reached(now, nudges[kind]) and not stamped_today(state, kind, today):
            return Decision(ACTION_NUDGE, kind)

    if clock_time_reached(now, nudges["summary"]) and not stamped_today(state, STAMP_SUMMARY, today):
        return Decision(ACTION_SUMMARY)

    if not within_active_hours(now, schedule, state["away_days"]):
        return None

    if not stamped_today(state, STAMP_RETEST, today) and retest_due(state, events, today, config["training"]["retest_days"]):
        return Decision(ACTION_RETEST)

    if not state["next_due"]:
        return Decision(ACTION_SCHEDULE_FIRST)

    if now.timestamp() < state["next_due"] or busy_reason:
        return None

    pending = state.get("pending")

    if pending:
        reminder_seconds = schedule["reminder_minutes"] * SECONDS_PER_MINUTE

        if now.timestamp() - pending.get("shown_at", 0) >= reminder_seconds:
            return Decision(ACTION_REMIND, pending)

        return None

    challenge = choose_challenge(state, pack, config["training"], config["profile"]["skills"], events, now, chooser)

    return Decision(ACTION_CHALLENGE, challenge) if challenge else None
