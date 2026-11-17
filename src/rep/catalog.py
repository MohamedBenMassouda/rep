import json
import random
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

DEFAULT_PACK_RESOURCE = "default_pack.json"
SKILL_GROUP = "skill"
UNIT_SUFFIXES = {"reps": "reps", "reps_per_side": "per side", "seconds": "s", "tries": "tries"}
REQUIRED_EXERCISE_FIELDS = ("name", "unit", "start", "step", "top", "cue")


class PackError(ValueError):
    pass


@dataclass(frozen=True)
class Exercise:
    identifier: str
    name: str
    unit: str
    start: int
    step: int
    top: int
    cue: str


@dataclass(frozen=True)
class Ladder:
    identifier: str
    group: str
    title: str
    exercise_identifiers: tuple


@dataclass(frozen=True)
class Pack:
    name: str
    groups: tuple
    exercises: dict
    ladders: dict
    skills: dict
    bosses: tuple
    test: tuple
    lines: dict
    muscles: dict

    def ladders_in_group(self, group):
        return [ladder for ladder in self.ladders.values() if ladder.group == group]

    def ladder_containing(self, exercise_identifier):
        for ladder in list(self.ladders.values()) + list(self.skills.values()):

            if exercise_identifier in ladder.exercise_identifiers:
                return ladder

        raise PackError(f"exercise {exercise_identifier!r} is on no ladder")

    def random_line(self, kind, chooser=random):
        candidates = self.lines.get(kind, ())

        return chooser.choice(candidates) if candidates else ""


def format_amount(exercise, target):
    suffix = UNIT_SUFFIXES[exercise.unit]

    return f"{target} {suffix}" if exercise.unit != "seconds" else f"{target}{suffix}"


def skill_progress(pack, ladder, exercise_identifier):
    exercise = pack.exercises[exercise_identifier]
    position = ladder.exercise_identifiers.index(exercise_identifier)
    step = f"Step {position + 1} of {len(ladder.exercise_identifiers)} to the {ladder.title}"
    has_next_rung = position + 1 < len(ladder.exercise_identifiers)

    if not has_next_rung:
        return f"{step}, the skill itself"

    next_exercise = pack.exercises[ladder.exercise_identifiers[position + 1]]

    return f"{step}. {format_amount(exercise, exercise.top)} unlocks {next_exercise.name}"


def load_pack(pack_file=None):
    if pack_file is None:
        raw_text = resources.files("rep.data").joinpath(DEFAULT_PACK_RESOURCE).read_text()
    else:
        raw_text = Path(pack_file).read_text()

    return parse_pack(json.loads(raw_text))


def parse_pack(raw):
    exercises = {}

    for identifier, fields in raw["exercises"].items():
        missing = [field for field in REQUIRED_EXERCISE_FIELDS if field not in fields]

        if missing:
            raise PackError(f"exercise {identifier!r} misses {', '.join(missing)}")

        if fields["unit"] not in UNIT_SUFFIXES:
            raise PackError(f"exercise {identifier!r} has unknown unit {fields['unit']!r}")

        exercises[identifier] = Exercise(identifier, **{field: fields[field] for field in REQUIRED_EXERCISE_FIELDS})

    ladders = {}

    for group, group_ladders in raw["ladders"].items():
        for ladder_identifier, exercise_identifiers in group_ladders.items():
            ladders[ladder_identifier] = Ladder(ladder_identifier, group, ladder_identifier, tuple(exercise_identifiers))

    skills = {
        skill_identifier: Ladder(skill_identifier, SKILL_GROUP, fields["title"], tuple(fields["ladder"]))
        for skill_identifier, fields in raw.get("skills", {}).items()
    }
    pack = Pack(
        name=raw["name"],
        groups=tuple(raw["groups"]),
        exercises=exercises,
        ladders=ladders,
        skills=skills,
        bosses=tuple(raw.get("bosses", ())),
        test=tuple(raw.get("test", ())),
        lines={kind: tuple(lines) for kind, lines in raw.get("lines", {}).items()},
        muscles=raw.get("muscles", {}),
    )
    validate_references(pack)

    return pack


def validate_references(pack):
    referenced = [identifier for ladder in list(pack.ladders.values()) + list(pack.skills.values())
                  for identifier in ladder.exercise_identifiers]
    referenced += list(pack.bosses) + list(pack.test)
    unknown = sorted({identifier for identifier in referenced if identifier not in pack.exercises})

    if unknown:
        raise PackError(f"unknown exercises referenced: {', '.join(unknown)}")

    for ladder in pack.ladders.values():

        if ladder.group not in pack.groups:
            raise PackError(f"ladder {ladder.identifier!r} is in unknown group {ladder.group!r}")

    for muscle, weights in pack.muscles.items():
        unknown_groups = sorted(group for group in weights if group not in pack.groups)

        if unknown_groups:
            raise PackError(f"muscle {muscle!r} is in unknown groups {', '.join(unknown_groups)}")
