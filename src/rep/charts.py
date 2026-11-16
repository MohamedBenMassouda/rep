from rep.catalog import format_amount
from rep.maxtest import test_history
from rep.progression import cap_usage, current_exercise, streak_days, target_of
from rep.store import EVENT_SET

SPARK_BLOCKS = "▁▂▃▄▅▆▇█"
HISTORY_POINTS = 16
NAME_WIDTH = 46
AMOUNT_WIDTH = 14
BOLD = "\033[1m"
BLUE = "\033[1;34m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def sparkline(values):
    if not values:
        return ""

    low, high = min(values), max(values)
    span = (high - low) or 1

    return "".join(SPARK_BLOCKS[round((value - low) / span * (len(SPARK_BLOCKS) - 1))] for value in values)


def ladder_amounts(events, ladder):
    return [event["amount"] for event in events
            if event["type"] == EVENT_SET and event.get("ladder") == ladder.identifier and isinstance(event.get("amount"), int)]


def next_step_text(pack, ladder, exercise_identifier):
    position = ladder.exercise_identifiers.index(exercise_identifier)

    if position + 1 >= len(ladder.exercise_identifiers):
        return "top of the ladder: slow the tempo or add a backpack"

    next_exercise = pack.exercises[ladder.exercise_identifiers[position + 1]]

    return f"→ {next_exercise.name} at {pack.exercises[exercise_identifier].top}"


def stats_text(app, with_history=False):
    today = app.clock().date()
    training = app.config["training"]
    usage = cap_usage(app.events, app.pack.groups, training["session_allowances"], today)
    week = ", ".join(f"{group} {usage[group]}/{training['weekly_caps'].get(group, 0)}" for group in app.pack.groups)
    streak = streak_days(app.events, today, training["streak_minimum"])
    lines = [f"{BOLD}Streak {streak} days · week: {week}{RESET}", ""]
    sections = [(group.upper(), app.pack.ladders_in_group(group)) for group in app.pack.groups]
    sections.append(("SKILLS", [app.pack.skills[skill] for skill in app.config["profile"]["skills"] if skill in app.pack.skills]))

    for title, ladders in sections:
        lines.append(f"{BLUE}{title}{RESET}")

        for ladder in ladders:
            exercise_identifier = current_exercise(app.state, ladder)
            exercise = app.pack.exercises[exercise_identifier]
            amount = format_amount(exercise, target_of(app.state, app.pack, exercise_identifier, app.scale))
            history = sparkline(ladder_amounts(app.events, ladder)[-HISTORY_POINTS:]) if with_history else ""
            lines.append(f"  {exercise.name:{NAME_WIDTH}} {amount:{AMOUNT_WIDTH}} {history:{HISTORY_POINTS}}  "
                         f"{YELLOW}{next_step_text(app.pack, ladder, exercise_identifier)}{RESET}")

        lines.append("")

    if with_history:
        lines += test_comparison(app)

    return "\n".join(lines)


def test_comparison(app):
    tests = test_history(app.events)

    if not tests:
        return ["No max test yet: run `rep test`."]

    latest = tests[-1]
    previous = tests[-2] if len(tests) > 1 else None
    header = f"{BOLD}Max test {latest['day']}" + (f" vs {previous['day']}" if previous else "") + RESET
    rows = [header]

    for exercise_identifier, result in latest["results"].items():
        before = previous["results"].get(exercise_identifier) if previous else None
        change = f"  ({result - before:+d})" if before is not None else ""
        rows.append(f"  {app.pack.exercises[exercise_identifier].name:{NAME_WIDTH}} {result}{change}")

    return rows
