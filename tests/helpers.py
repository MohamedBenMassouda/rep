import datetime
import random

from rep.catalog import load_pack
from rep.config import DEFAULTS, merge
from rep.store import empty_state, new_event

FIXED_NOW = datetime.datetime(2026, 11, 18, 11, 0)
SEED = 7
ADVANCED_SCALE = 1.0


def default_pack():
    return load_pack()


def config_with(**sections):
    return merge(DEFAULTS, {"profile": {"body_weight_kg": 80, "level": "advanced",
                                        "skills": ["handstand", "one_arm_pull_up"]}, **sections})


def seeded_random():
    return random.Random(SEED)


def fresh_state():
    return empty_state()


def event_at(event_type, now=FIXED_NOW, **fields):
    return new_event(event_type, now=now, **fields)
