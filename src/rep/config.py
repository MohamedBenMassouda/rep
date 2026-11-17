import copy
import tomllib

LEVEL_SCALES = {"beginner": 0.4, "intermediate": 0.7, "advanced": 1.0}
NOTIFIERS = ("auto", "quickshell", "desktop", "terminal")
PROTEIN_GRAMS_PER_KILOGRAM = (1.6, 2.0)
TIME_FORMAT_LENGTH = 5

DEFAULTS = {
    "profile": {"body_weight_kg": 0, "level": "intermediate", "skills": []},
    "schedule": {
        "start_hour": 10,
        "end_hour": 22,
        "minimum_gap_minutes": 45,
        "maximum_gap_minutes": 75,
        "first_challenge_minutes": [5, 30],
        "snooze_minutes": 10,
        "reminder_minutes": 15,
    },
    "training": {
        "weekly_caps": {"push": 10, "pull": 10, "legs": 6, "core": 6},
        "session_allowances": {
            "upper": {"push": 6, "pull": 6},
            "legs": {"legs": 6},
            "full": {"push": 4, "pull": 4, "legs": 4, "core": 4},
        },
        "routine": {},
        "sets_per_muscle": 3,
        "skill_share_training_day": 0.7,
        "skill_share_rest_day": 0.3,
        "boss_after_hour": 15,
        "boss_chance": 0.25,
        "streak_minimum": 4,
        "retest_days": 42,
        "pack_file": "",
    },
    "nudges": {"protein": "20:00", "bedtime": "23:30", "summary": "22:00"},
    "display": {"notifier": "auto", "quickshell_kind": "workout", "line_command": ""},
    "conditions": {"pause_files": [], "check_microphone": True, "check_screen_share": True},
    "sync": {"url": "", "token": ""},
}


class ConfigMissing(RuntimeError):
    pass


def merge(defaults, overrides):
    merged = copy.deepcopy(defaults)

    for key, value in overrides.items():

        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge(merged[key], value)
        else:
            merged[key] = value

    return merged


def load_config(paths):
    if not paths.config_file.exists():
        raise ConfigMissing(f"no config yet: run `rep init` ({paths.config_file})")

    with open(paths.config_file, "rb") as config_stream:
        config = merge(DEFAULTS, tomllib.load(config_stream))

    if not config["profile"]["body_weight_kg"]:
        raise ConfigMissing(f"your profile isn't set up yet: run `rep init` ({paths.config_file})")

    return config


def toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (int, float)):
        return repr(value)

    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"

    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {toml_value(item)}" for key, item in value.items()) + " }"

    raise TypeError(f"cannot write {type(value).__name__} to TOML")


def to_toml(config):
    sections = []

    for section, values in config.items():
        lines = [f"[{section}]"] + [f"{key} = {toml_value(value)}" for key, value in values.items()]
        sections.append("\n".join(lines))

    return "\n\n".join(sections) + "\n"


def save_config(paths, config):
    paths.config_directory.mkdir(parents=True, exist_ok=True)
    temporary_file = paths.config_file.with_suffix(".tmp")
    temporary_file.write_text(to_toml(config))
    temporary_file.replace(paths.config_file)


def level_scale(config):
    return LEVEL_SCALES.get(config["profile"]["level"], LEVEL_SCALES["intermediate"])


def protein_range_grams(config):
    weight = config["profile"]["body_weight_kg"]

    return tuple(round(weight * grams) for grams in PROTEIN_GRAMS_PER_KILOGRAM)


def is_clock_time(text):
    if text == "off":
        return True

    if len(text) != TIME_FORMAT_LENGTH or text[2] != ":":
        return False

    hours, minutes = text[:2], text[3:]

    return hours.isdigit() and minutes.isdigit() and int(hours) < 24 and int(minutes) < 60
