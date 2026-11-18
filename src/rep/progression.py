import datetime
from dataclasses import dataclass

from rep.catalog import SKILL_GROUP
from rep.store import EVENT_SESSION, EVENT_SET, completed_counts

RATING_EASY = 3
RATING_STEADY = 1
RATING_FAILURE = 0
RATINGS = (RATING_EASY, RATING_STEADY, RATING_FAILURE)
STEADY_ANSWERS_TO_ADVANCE = 3
MINIMUM_TARGET = 1
KIND_HARD = "hard"
KIND_SKILL = "skill"
KIND_BOSS = "boss"
DAYS_IN_WEEK = 7


@dataclass(frozen=True)
class Challenge:
    kind: str
    group: str
    ladder_identifier: str
    exercise_identifier: str


def start_target(exercise, scale):
    return max(MINIMUM_TARGET, round(exercise.start * scale))


def target_of(state, pack, exercise_identifier, scale):
    exercise = pack.exercises[exercise_identifier]

    return state["targets"].get(exercise_identifier, start_target(exercise, scale))


def current_exercise(state, ladder):
    rung = min(state["rungs"].get(ladder.identifier, 0), len(ladder.exercise_identifiers) - 1)

    return ladder.exercise_identifiers[rung]


def apply_rating(state, pack, exercise_identifier, rating, scale, done=None):
    exercise = pack.exercises[exercise_identifier]
    ladder = pack.ladder_containing(exercise_identifier)
    target = target_of(state, pack, exercise_identifier, scale) if done is None else max(MINIMUM_TARGET, done)
    steady = state["steady_answers"].get(exercise_identifier, 0)

    if rating >= RATING_EASY:
        target, steady = target + exercise.step, 0
    elif rating >= RATING_STEADY:
        steady += 1

        if steady >= STEADY_ANSWERS_TO_ADVANCE:
            target, steady = target + exercise.step, 0
    else:
        steady = 0

    state["targets"][exercise_identifier] = target
    state["steady_answers"][exercise_identifier] = steady
    position = ladder.exercise_identifiers.index(exercise_identifier)
    has_next_rung = position + 1 < len(ladder.exercise_identifiers)

    if target >= exercise.top and has_next_rung:
        state["rungs"][ladder.identifier] = position + 1

        return ladder.exercise_identifiers[position + 1]

    return None


def week_start(day):
    return day - datetime.timedelta(days=day.weekday())


def cap_usage(events, groups, session_allowances, today):
    usage = {group: 0 for group in groups}
    this_week = week_start(today)

    for event in events:
        event_day = datetime.date.fromisoformat(event["day"])

        if week_start(event_day) != this_week:
            continue

        if event["type"] == EVENT_SET and event.get("kind") == KIND_HARD and event.get("group") in usage:
            usage[event["group"]] += 1
        elif event["type"] == EVENT_SESSION:
            for group, sets in session_allowances.get(event["session"], {}).items():

                if group in usage:
                    usage[group] += sets

    return usage


def trained_groups(events, session_groups, today):
    groups = set()

    for event in events:

        if event["type"] == EVENT_SESSION and event["day"] == today.isoformat():
            groups |= set(session_groups.get(event["session"], ()))

    return groups


def boss_done_this_week(events, today):
    this_week = week_start(today)

    return any(event["type"] == EVENT_SET and event.get("kind") == KIND_BOSS
               and week_start(datetime.date.fromisoformat(event["day"])) == this_week for event in events)


def rotation_from(groups, last_group):
    if last_group not in groups:
        return list(groups)

    start = (groups.index(last_group) + 1) % len(groups)

    return list(groups[start:]) + list(groups[:start])


def resting_groups(state, today):
    return {group for group, until in state["rested"].items() if until > today.isoformat()}


def choose_challenge(state, pack, training, profile_skills, events, now, chooser):
    today = now.date()
    session_groups = {session: tuple(allowance) for session, allowance in training["session_allowances"].items()}
    resting = resting_groups(state, today)
    trained = trained_groups(events, session_groups, today)
    usage = cap_usage(events, pack.groups, training["session_allowances"], today)
    is_rest_day = not trained
    skills = [] if SKILL_GROUP in resting else [pack.skills[skill] for skill in profile_skills if skill in pack.skills]
    bosses = [boss for boss in pack.bosses if pack.ladder_containing(boss).group not in resting]
    boss_allowed = (is_rest_day and bosses and now.hour >= training["boss_after_hour"]
                    and not boss_done_this_week(events, today))

    if boss_allowed and chooser.random() < training["boss_chance"]:
        exercise_identifier = chooser.choice(bosses)
        ladder = pack.ladder_containing(exercise_identifier)

        return Challenge(KIND_BOSS, ladder.group, ladder.identifier, exercise_identifier)

    skill_share = training["skill_share_rest_day"] if is_rest_day else training["skill_share_training_day"]
    open_groups = [group for group in rotation_from(pack.groups, state.get("last_group"))
                   if group not in trained | resting and usage[group] < training["weekly_caps"].get(group, 0)]
    wants_skill = bool(skills) and chooser.random() < skill_share

    if wants_skill or not open_groups:

        if not skills:
            return None

        ladder = chooser.choice(skills)

        return Challenge(KIND_SKILL, SKILL_GROUP, ladder.identifier, current_exercise(state, ladder))

    group = open_groups[0]
    recent_ladders = {event.get("ladder") for event in events[-len(pack.ladders_in_group(group)) * 2:]}
    ladders = pack.ladders_in_group(group)
    fresh = [ladder for ladder in ladders if ladder.identifier not in recent_ladders] or ladders
    ladder = chooser.choice(fresh)

    return Challenge(KIND_HARD, group, ladder.identifier, current_exercise(state, ladder))


def streak_days(events, today, minimum):
    return streak_from_counts(completed_counts(events), today, minimum)


def streak_from_counts(counts, today, minimum):
    checked_day = today

    if counts.get(checked_day.isoformat(), 0) < minimum:
        checked_day -= datetime.timedelta(days=1)

    streak = 0

    while counts.get(checked_day.isoformat(), 0) >= minimum:
        streak += 1
        checked_day -= datetime.timedelta(days=1)

    return streak
