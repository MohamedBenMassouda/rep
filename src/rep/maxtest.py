from rep.catalog import SKILL_GROUP
from rep.store import EVENT_TEST

STRENGTH_TARGET_SHARE = 0.7
SKILL_TARGET_SHARE = 0.5
MINIMUM_REAL_REPS = 3
MINIMUM_REAL_SECONDS = 10
MINIMUM_TARGET = 1
QUESTION_UNITS = {"reps": "reps", "reps_per_side": "reps per side", "seconds": "seconds", "tries": "tries"}
TEST_INSTRUCTIONS = "Max test: one all-out set each, rest 2-3 minutes between."
QUESTION_RESULT = "result"
QUESTION_SKILL = "skill"


def result_question(exercise):
    return f"{exercise.name}: max {QUESTION_UNITS[exercise.unit]}"


def skill_question(ladder):
    return f"{ladder.title}: where are you?"


def skill_options(pack, ladder):
    return [pack.exercises[exercise_identifier].name for exercise_identifier in ladder.exercise_identifiers]


def skill_step(answer, ladder):
    valid = answer.isdigit() and 1 <= int(answer) <= len(ladder.exercise_identifiers)

    return int(answer) - 1 if valid else None


def test_questions(pack, skills):
    questions = [(QUESTION_RESULT, exercise_identifier) for exercise_identifier in pack.test]

    return questions + [(QUESTION_SKILL, skill) for skill in skills if skill in pack.skills]


def counts_as_real(exercise, result):
    minimum = MINIMUM_REAL_SECONDS if exercise.unit == "seconds" else MINIMUM_REAL_REPS

    return result >= minimum


def ask_results(pack, read, write):
    write(f"{TEST_INSTRUCTIONS} Enter skips one.\n")
    results = {}

    for exercise_identifier in pack.test:
        answer = read(f"  {result_question(pack.exercises[exercise_identifier])}: ").strip()

        if answer.isdigit():
            results[exercise_identifier] = int(answer)

    return results


def ask_skill_steps(pack, skills, read, write):
    steps = {}

    for skill_identifier in skills:
        ladder = pack.skills[skill_identifier]
        write(f"\n  {skill_question(ladder)}")

        for number, name in enumerate(skill_options(pack, ladder), start=1):
            write(f"    {number}. {name}")

        step = skill_step(read("  Number (Enter = 1): ").strip(), ladder)
        steps[skill_identifier] = 0 if step is None else step

    return steps


def apply_results(state, pack, results, skill_steps):
    for skill_identifier, step in skill_steps.items():
        state["rungs"][skill_identifier] = step

    for ladder in list(pack.ladders.values()) + list(pack.skills.values()):
        tested = [identifier for identifier in ladder.exercise_identifiers
                  if identifier in results and counts_as_real(pack.exercises[identifier], results[identifier])]

        if not tested or ladder.identifier in skill_steps:
            continue

        hardest = tested[-1]
        share = SKILL_TARGET_SHARE if ladder.group == SKILL_GROUP else STRENGTH_TARGET_SHARE
        state["rungs"][ladder.identifier] = ladder.exercise_identifiers.index(hardest)
        state["targets"][hardest] = max(MINIMUM_TARGET, round(results[hardest] * share))


def ask_test(app, read=input, write=print):
    results = ask_results(app.pack, read, write)
    skill_steps = ask_skill_steps(app.pack, [skill for skill in app.config["profile"]["skills"] if skill in app.pack.skills],
                                  read, write)

    return results, skill_steps


def run_test(app, read=input, write=print):
    results, skill_steps = ask_test(app, read, write)
    write("\n" + app.apply_test(results, skill_steps))

    return results


def test_history(events):
    return [event for event in events if event["type"] == EVENT_TEST]
