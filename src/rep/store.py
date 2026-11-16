import datetime
import json
import time
import uuid

STATE_VERSION = 1
EVENT_SET = "set"
EVENT_SKIP = "skip"
EVENT_SESSION = "session"
EVENT_TEST = "test"


def empty_state():
    return {
        "version": STATE_VERSION,
        "targets": {},
        "steady_answers": {},
        "rungs": {},
        "best": {},
        "pending": None,
        "next_due": 0,
        "last_group": None,
        "stamps": {},
    }


def load_state(paths):
    try:
        loaded = json.loads(paths.state_file.read_text())
    except (OSError, ValueError):
        return empty_state()

    state = empty_state()
    state.update({key: value for key, value in loaded.items() if key in state})

    return state


def save_state(paths, state):
    paths.state_directory.mkdir(parents=True, exist_ok=True)
    temporary_file = paths.state_file.with_suffix(".tmp")
    temporary_file.write_text(json.dumps(state, indent=1))
    temporary_file.replace(paths.state_file)


def new_event(event_type, now=None, **fields):
    moment = now or datetime.datetime.now()

    return {
        "id": uuid.uuid4().hex,
        "type": event_type,
        "time": int(moment.timestamp()) if now else int(time.time()),
        "day": moment.date().isoformat(),
        **fields,
    }


def append_event(paths, event):
    paths.state_directory.mkdir(parents=True, exist_ok=True)

    with open(paths.events_file, "a") as events_stream:
        events_stream.write(json.dumps(event) + "\n")

    return event


def load_events(paths):
    try:
        lines = paths.events_file.read_text().splitlines()
    except OSError:
        return []

    events = []

    for line in lines:

        if not line.strip():
            continue

        try:
            events.append(json.loads(line))
        except ValueError:
            continue

    return events


def write_events(paths, events):
    paths.state_directory.mkdir(parents=True, exist_ok=True)
    temporary_file = paths.events_file.with_suffix(".tmp")
    temporary_file.write_text("".join(json.dumps(event) + "\n" for event in events))
    temporary_file.replace(paths.events_file)
