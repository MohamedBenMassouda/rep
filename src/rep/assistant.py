import copy
import datetime

from rep.ai import model_object, model_request, model_text
from rep.app import MAXIMUM_REST_DAYS, RATING_LABELS
from rep.catalog import REQUIRED_EXERCISE_FIELDS, SKILL_GROUP, UNIT_SUFFIXES, PackError, format_amount, parse_pack
from rep.charts import phone_stats_text
from rep.maxtest import test_history
from rep.progression import KIND_HARD, current_exercise
from rep.routine import RoutineError, describe_sessions, parse_day
from rep.store import EVENT_SESSION, EVENT_SET, EVENT_SKIP

COACH_HISTORY_DAYS = 7
REPS_NOT_SAID = 0
FEELING_NOT_SAID = "not said"
NOTE_DONE = "done"
NOTE_SKIP = "skip"
NOTE_UNCLEAR = "unclear"
NOTE_ANSWERS = (NOTE_DONE, NOTE_SKIP, NOTE_UNCLEAR)
MINIMUM_REST_DAYS = 1
TESTS_COMPARED = 2
MAXIMUM_ROUTINE_DAYS = 7
SCHEMA_TEXT = {"type": "string"}
SCHEMA_INTEGER = {"type": "integer"}
NO_COACH_ANSWER = "The coach didn't answer. Try again in a minute."
COACH_INSTRUCTIONS = (
    "You coach one person who trains calisthenics with short hard sets spread through the day. "
    "Review their last week from the data you are given. Write plain text for a chat message: no Markdown, "
    "no asterisks, no headings. At most 6 short lines, each starting with '• ': what went well, what stalls "
    "(targets that don't move, failures, skips), the balance between the groups against their weekly caps, and "
    "one or two concrete changes for next week. Use the exercise names given and never invent numbers. "
    "When nothing is logged, say the week is empty instead of calling it skipped."
)
NOTE_INSTRUCTIONS = (
    "Read a short message about one exercise set and fill in the answer. answer: done when they did the set, "
    "skip when they didn't or won't, unclear otherwise. reps: the reps or seconds they say they did, 0 when they "
    "don't say. feeling: the option that matches how the set felt, the failure option only when they say they "
    f"couldn't finish a rep or went to failure, '{FEELING_NOT_SAID}' when they don't say."
)
PAIN_INSTRUCTIONS = (
    "You help one person who trains calisthenics with short hard sets spread through the day. They describe pain, "
    "an injury or a constraint. advice: short, careful advice in plain text, no Markdown, at most 4 lines; tell them "
    "to see a professional when it sounds serious. rest: the training groups that should rest, empty when none "
    f"needs to. days: how many days they rest, {MINIMUM_REST_DAYS} to {MAXIMUM_REST_DAYS}."
)
PACK_INSTRUCTIONS = (
    "You extend the exercise pack of a calisthenics app. A ladder is a progression from easier to harder movements "
    "in one group; reaching an exercise's top target moves the athlete to the next rung. A skill is a ladder towards "
    "one skill. Add only what the request asks for: new exercises with new snake_case identifiers, placed on new "
    "ladders in an existing group or on new skills. Never reuse or change an existing identifier. start: a realistic "
    "first target for an intermediate athlete; step: the increase after an easy set (1 for reps, 5 for seconds); "
    "top: where the ladder moves on; cue: one short form cue."
)
ROUTINE_INSTRUCTIONS = (
    "Turn a description of someone's training week into training days for a calisthenics app. Each day gets a short "
    "lowercase name (letters, digits, - or _), like push or legs-day, and the muscles it trains, taken only from the "
    f"list. At most {MAXIMUM_ROUTINE_DAYS} days. Leave rest days out."
)


def strict_object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def text_choice(options):
    return {"type": "string", "enum": list(options)}


def list_of(item):
    return {"type": "array", "items": item}


def rating_label(kind, rating):
    labels = RATING_LABELS.get(kind, RATING_LABELS[KIND_HARD])

    return next((label for label, value in labels if value == rating), str(rating))


def event_text(pack, event):
    exercise = pack.exercises.get(event.get("exercise"))
    name = exercise.name if exercise else event.get("exercise", "")

    if event["type"] == EVENT_SESSION:
        return f"training day {event['session']}"

    if event["type"] == EVENT_SKIP:
        return f"skipped {name}"

    amount = event.get("amount")
    amount_text = format_amount(exercise, amount) if exercise and isinstance(amount, int) else str(amount)

    return f"{name} {amount_text} ({rating_label(event.get('kind'), event.get('rating'))})"


def history_lines(app, days):
    first_day = (app.clock().date() - datetime.timedelta(days=days)).isoformat()
    per_day = {}

    for event in app.events:

        if event["type"] in (EVENT_SET, EVENT_SKIP, EVENT_SESSION) and event["day"] >= first_day:
            per_day.setdefault(event["day"], []).append(event_text(app.pack, event))

    return [f"{day}: {'; '.join(entries)}" for day, entries in sorted(per_day.items())] or ["nothing logged"]


def test_lines(app):
    lines = []

    for test in test_history(app.events)[-TESTS_COMPARED:]:
        results = ", ".join(f"{app.pack.exercises[identifier].name} {result}"
                            for identifier, result in test["results"].items() if identifier in app.pack.exercises)
        lines.append(f"Max test {test['day']}: {results or 'no results'}")

    return lines or ["No max test yet"]


def coach_brief(app):
    training, profile = app.config["training"], app.config["profile"]
    skills = ", ".join(app.pack.skills[skill].title for skill in profile["skills"] if skill in app.pack.skills)
    routine = describe_sessions(training, training["session_allowances"])
    caps = ", ".join(f"{group} {cap}" for group, cap in training["weekly_caps"].items())

    return "\n".join([f"Level: {profile['level']}. Skills: {skills or 'none'}.",
                      f"Training days: {'; '.join(f'{name}: {muscles}' for name, muscles in routine.items())}",
                      f"Weekly caps of hard sets: {caps}", "", phone_stats_text(app), "",
                      f"Last {COACH_HISTORY_DAYS} days:"] + history_lines(app, COACH_HISTORY_DAYS) + [""]
                     + test_lines(app))


def coach_request(app):
    return model_request(app.config["ai"], COACH_INSTRUCTIONS, coach_brief(app))


def coach_reply(response):
    return model_text(response) or NO_COACH_ANSWER


def feeling_labels(kind):
    return [label for label, _ in RATING_LABELS.get(kind, RATING_LABELS[KIND_HARD])]


def note_request(app, note):
    pending = app.state["pending"]
    labels = feeling_labels(pending["kind"])
    schema = strict_object({"answer": text_choice(NOTE_ANSWERS), "reps": SCHEMA_INTEGER,
                            "feeling": text_choice(labels + [FEELING_NOT_SAID])})
    question = (f"The set: {app.pack.exercises[pending['exercise']].name}, target {app.amount(pending['exercise'])}.\n"
                f"Feeling options: {', '.join(labels)}.\nMessage: {note}")

    return model_request(app.config["ai"], NOTE_INSTRUCTIONS, question, schema)


def note_answer(response, kind):
    answer = model_object(response)

    if not answer or answer.get("answer") not in NOTE_ANSWERS:
        return None

    reps = answer.get("reps")
    ratings = dict(RATING_LABELS.get(kind, RATING_LABELS[KIND_HARD]))

    return {"answer": answer["answer"], "reps": reps if isinstance(reps, int) and reps > REPS_NOT_SAID else None,
            "rating": ratings.get(answer.get("feeling"))}


def rest_groups(pack):
    return list(pack.groups) + [SKILL_GROUP]


def current_names(app, group):
    return ", ".join(app.pack.exercises[current_exercise(app.state, ladder)].name
                     for ladder in app.pack.ladders_in_group(group))


def group_lines(app):
    lines = [f"{group}: {current_names(app, group)}" for group in app.pack.groups]
    skills = [app.pack.skills[skill].title for skill in app.config["profile"]["skills"] if skill in app.pack.skills]

    return lines + [f"{SKILL_GROUP}: {', '.join(skills) or 'none'}"]


def pain_request(app, note):
    schema = strict_object({"advice": SCHEMA_TEXT, "rest": list_of(text_choice(rest_groups(app.pack))),
                            "days": SCHEMA_INTEGER})
    question = "Groups and their current exercises:\n" + "\n".join(group_lines(app)) + f"\n\nMessage: {note}"

    return model_request(app.config["ai"], PAIN_INSTRUCTIONS, question, schema)


def pain_answer(response, pack):
    answer = model_object(response)

    if not answer or not isinstance(answer.get("advice"), str) or not isinstance(answer.get("days"), int):
        return None

    groups = [group for group in rest_groups(pack) if group in (answer.get("rest") or [])]
    days = min(max(answer["days"], MINIMUM_REST_DAYS), MAXIMUM_REST_DAYS)

    return {"advice": answer["advice"].strip(), "rest": groups, "days": days}


def exercise_summary(identifier, fields):
    return f"{identifier} ({fields['name']}, {fields['unit']} {fields['start']}→{fields['top']})"


def pack_brief(pack_raw, wish):
    exercises = pack_raw["exercises"]
    ladders = [f"{group}/{ladder}: " + ", ".join(exercise_summary(identifier, exercises[identifier])
                                                for identifier in identifiers)
               for group, group_ladders in pack_raw["ladders"].items() for ladder, identifiers in group_ladders.items()]
    skills = [f"{skill}: " + ", ".join(exercise_summary(identifier, exercises[identifier])
                                       for identifier in fields["ladder"])
              for skill, fields in pack_raw.get("skills", {}).items()]

    return "\n".join([f"Groups: {', '.join(pack_raw['groups'])}", f"Units: {', '.join(UNIT_SUFFIXES)}",
                      "Ladders:"] + ladders + ["Skills:"] + skills + ["", f"Request: {wish}"])


def pack_request(settings, pack_raw, wish):
    exercise = strict_object({"identifier": SCHEMA_TEXT, "name": SCHEMA_TEXT, "unit": text_choice(UNIT_SUFFIXES),
                              "start": SCHEMA_INTEGER, "step": SCHEMA_INTEGER, "top": SCHEMA_INTEGER,
                              "cue": SCHEMA_TEXT})
    ladder = strict_object({"group": text_choice(pack_raw["groups"]), "identifier": SCHEMA_TEXT,
                            "exercises": list_of(SCHEMA_TEXT)})
    skill = strict_object({"identifier": SCHEMA_TEXT, "title": SCHEMA_TEXT, "exercises": list_of(SCHEMA_TEXT)})
    schema = strict_object({"exercises": list_of(exercise), "ladders": list_of(ladder), "skills": list_of(skill)})

    return model_request(settings, PACK_INSTRUCTIONS, pack_brief(pack_raw, wish), schema)


def taken_identifiers(pack_raw):
    ladders = {ladder for group_ladders in pack_raw["ladders"].values() for ladder in group_ladders}

    return set(pack_raw["exercises"]) | ladders | set(pack_raw.get("skills", {}))


def checked_exercise(exercise):
    fields = {field: exercise[field] for field in REQUIRED_EXERCISE_FIELDS}

    if not (0 < fields["start"] <= fields["top"] and fields["step"] > 0):
        raise PackError(f"exercise {exercise['identifier']!r} needs 0 < start <= top and a positive step")

    return fields


def pack_with_additions(pack_raw, answer):
    if not answer:
        raise PackError("the AI didn't answer")

    extended = copy.deepcopy(pack_raw)
    taken = taken_identifiers(pack_raw)

    try:
        additions = {exercise["identifier"]: checked_exercise(exercise) for exercise in answer["exercises"]}
        rungs = [(ladder["identifier"], ladder["exercises"]) for ladder in answer["ladders"] + answer["skills"]]
    except (KeyError, TypeError) as problem:
        raise PackError(f"the suggestion is incomplete ({problem})") from problem

    clashes = sorted(taken & (set(additions) | {identifier for identifier, _ in rungs}))
    placed = [identifier for _, identifiers in rungs for identifier in identifiers]

    if clashes:
        raise PackError(f"the suggestion reuses existing identifiers: {', '.join(clashes)}")

    if not additions or sorted(placed) != sorted(additions):
        raise PackError("every new exercise must sit on exactly one new ladder or skill")

    extended["exercises"].update(additions)

    for ladder in answer["ladders"]:
        extended["ladders"].setdefault(ladder["group"], {})[ladder["identifier"]] = ladder["exercises"]

    for skill in answer["skills"]:
        extended.setdefault("skills", {})[skill["identifier"]] = {"title": skill["title"], "ladder": skill["exercises"]}

    parse_pack(extended)

    return extended, [exercise_summary(identifier, fields) for identifier, fields in additions.items()]


def routine_request(settings, pack, description):
    day = strict_object({"name": SCHEMA_TEXT, "muscles": list_of(text_choice(pack.muscles))})
    question = f"Muscles: {', '.join(pack.muscles)}\nWeek: {description}"

    return model_request(settings, ROUTINE_INSTRUCTIONS, question, strict_object({"days": list_of(day)}))


def drafted_routine(response, pack):
    answer = model_object(response)

    if not answer or not isinstance(answer.get("days"), list):
        return None

    routine = {}

    try:
        for day in answer["days"][:MAXIMUM_ROUTINE_DAYS]:
            name, muscles = parse_day(f"{day['name']}: {', '.join(day['muscles'])}", pack.muscles)
            routine[name] = muscles
    except (RoutineError, KeyError, TypeError):
        return None

    return routine or None
