from rep.config import DEFAULTS, LEVEL_SCALES, NOTIFIERS, is_clock_time, merge
from rep.routine import RoutineError, parse_day

MINIMUM_BODY_WEIGHT_KG = 30
MAXIMUM_BODY_WEIGHT_KG = 250
HOURS_IN_DAY = 24
CLEAR_ROUTINE = "none"


def ask(question, default, accept, read=input, write=print):
    while True:
        answer = read(f"{question} [{default}]: ").strip() or str(default)

        if accept(answer):
            return answer

        write("  That doesn't look right, try again.")


def is_weight(text):
    return text.replace(".", "", 1).isdigit() and MINIMUM_BODY_WEIGHT_KG <= float(text) <= MAXIMUM_BODY_WEIGHT_KG


def is_hour(text):
    return text.isdigit() and 0 <= int(text) < HOURS_IN_DAY


def chosen_skills(text, skill_identifiers):
    if text == "none":
        return []

    numbers = [part.strip() for part in text.split(",") if part.strip()]

    if not all(number.isdigit() and 1 <= int(number) <= len(skill_identifiers) for number in numbers):
        return None

    return [skill_identifiers[int(number) - 1] for number in numbers]


def ask_routine(pack, routine, read=input, write=print):
    write("\nYour training days, one per line as name: muscles (example: push: chest, shoulders, triceps).")
    write(f"  Muscles: {', '.join(muscle.replace('_', ' ') for muscle in pack.muscles)}")

    if routine:
        for session, muscles in routine.items():
            write(f"  now  {session}: {', '.join(muscles)}")

        write(f"  Empty line keeps these, {CLEAR_ROUTINE} goes back to upper / legs / full.")
    else:
        write("  Empty line keeps the built-in upper / legs / full sessions.")

    days = {}

    while True:
        line = read("  day: ").strip()

        if not line:
            return days or routine

        if line.lower() == CLEAR_ROUTINE and not days:
            return {}

        try:
            session, muscles = parse_day(line, pack.muscles)
        except RoutineError as problem:
            write(f"  {problem}, try again.")

            continue

        days[session] = muscles


def run_wizard(pack, existing=None, read=input, write=print):
    current = merge(DEFAULTS, existing or {})
    profile, schedule, nudges, display = current["profile"], current["schedule"], current["nudges"], current["display"]
    write("rep setup. Your answers stay in your config file on this computer.\n")
    weight = ask("Body weight in kg (for the protein target)", profile["body_weight_kg"] or 75, is_weight, read, write)
    level = ask(f"Level ({' / '.join(LEVEL_SCALES)})", profile["level"], lambda text: text in LEVEL_SCALES, read, write)
    skill_identifiers = list(pack.skills)

    for number, skill_identifier in enumerate(skill_identifiers, start=1):
        write(f"  {number}. {pack.skills[skill_identifier].title}")

    default_skills = ",".join(str(skill_identifiers.index(skill) + 1) for skill in profile["skills"] if skill in skill_identifiers) or "none"
    skills_answer = ask("Skills to practise (numbers, comma separated, or none)", default_skills,
                        lambda text: chosen_skills(text, skill_identifiers) is not None, read, write)
    routine = ask_routine(pack, current["training"]["routine"], read, write)
    start_hour = ask("Challenges from (hour)", schedule["start_hour"], is_hour, read, write)
    end_hour = ask("Challenges until (hour)", schedule["end_hour"],
                   lambda text: is_hour(text) and int(text) > int(start_hour), read, write)
    protein = ask("Protein check-in time (HH:MM or off)", nudges["protein"], is_clock_time, read, write)
    bedtime = ask("Bedtime reminder (HH:MM or off)", nudges["bedtime"], is_clock_time, read, write)
    summary = ask("Daily summary (HH:MM or off)", nudges["summary"], is_clock_time, read, write)
    notifier = ask(f"Show challenges with ({' / '.join(NOTIFIERS)})", display["notifier"], lambda text: text in NOTIFIERS, read, write)
    profile.update(body_weight_kg=float(weight), level=level, skills=chosen_skills(skills_answer, skill_identifiers))
    schedule.update(start_hour=int(start_hour), end_hour=int(end_hour))
    current["training"]["routine"] = routine
    nudges.update(protein=protein, bedtime=bedtime, summary=summary)
    display.update(notifier=notifier)

    return current
