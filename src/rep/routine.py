import re

SESSION_NAME_PATTERN = re.compile(r"[a-z0-9_-]+")
NAME_SEPARATOR = ":"
MUSCLE_SEPARATORS = re.compile(r"[,+&]|\band\b")
WORD_SEPARATORS = re.compile(r"[\s-]+")
PLURAL_SUFFIX = "s"


class RoutineError(ValueError):
    pass


def muscle_named(text, muscles):
    candidate = WORD_SEPARATORS.sub("_", text.strip().lower())

    for spelling in (candidate, candidate + PLURAL_SUFFIX, candidate.removesuffix(PLURAL_SUFFIX)):

        if spelling in muscles:
            return spelling

    return None


def parse_muscles(text, muscles):
    named = []

    for part in MUSCLE_SEPARATORS.split(text):

        if not part.strip():
            continue

        muscle = muscle_named(part, muscles)

        if muscle is None:
            raise RoutineError(f"unknown muscle {part.strip()!r}")

        if muscle not in named:
            named.append(muscle)

    if not named:
        raise RoutineError("name at least one muscle")

    return named


def parse_day(text, muscles):
    name, separator, muscle_text = text.partition(NAME_SEPARATOR)
    name = name.strip().lower()

    if not separator or not SESSION_NAME_PATTERN.fullmatch(name):
        raise RoutineError("write it as name: muscles, the name in letters, digits, - or _")

    return name, parse_muscles(muscle_text, muscles)


def routine_allowances(routine, muscles, sets_per_muscle, weekly_caps):
    allowances = {}

    for session, session_muscles in routine.items():
        sets = {}

        for muscle in parse_muscles(", ".join(session_muscles), muscles):
            for group, weight in muscles[muscle].items():
                sets[group] = sets.get(group, 0) + weight * sets_per_muscle

        allowances[session] = {group: min(count, weekly_caps.get(group, count)) for group, count in sets.items()}

    return allowances


def session_allowances(training, pack):
    if not training["routine"]:
        return training["session_allowances"]

    try:
        return routine_allowances(training["routine"], pack.muscles, training["sets_per_muscle"],
                                  training["weekly_caps"])
    except RoutineError as problem:
        raise RoutineError(f"[training] routine: {problem}") from problem


def describe_sessions(training, allowances):
    routine = training["routine"]

    return {session: " + ".join(muscle.replace("_", " ") for muscle in routine[session]) if routine
            else " + ".join(groups) for session, groups in allowances.items()}
