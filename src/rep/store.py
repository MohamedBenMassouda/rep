import datetime
import json
import time
import uuid
from collections.abc import Sequence

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
        "last_test_day": None,
        "paused_until": 0,
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


class EventLog(Sequence):
    def __init__(self, load):
        self.load, self.loaded = load, None

    def records(self):
        if self.loaded is None:
            self.loaded = self.load()

        return self.loaded

    def __getitem__(self, index):
        return self.records()[index]

    def __len__(self):
        return len(self.records())

    def __iter__(self):
        return iter(self.records())

    def append(self, event):
        if self.loaded is not None:
            self.loaded.append(event)


def completed_counts(events):
    counts = {}

    for event in events:

        if event["type"] == EVENT_SET:
            counts[event["day"]] = counts.get(event["day"], 0) + 1

    return counts


class FileStore:
    def __init__(self, paths):
        self.paths = paths

    def completed_counts(self):
        return completed_counts(self.load_events())

    def load_state(self):
        return load_state(self.paths)

    def save_state(self, state):
        save_state(self.paths, state)

    def load_events(self):
        return load_events(self.paths)

    def append_event(self, event):
        return append_event(self.paths, event)


class MemoryStore:
    def __init__(self, state, events):
        self.state, self.events = state, list(events)

    def completed_counts(self):
        return completed_counts(self.events)

    def load_state(self):
        loaded = empty_state()
        loaded.update({key: value for key, value in self.state.items() if key in loaded})

        return loaded

    def save_state(self, state):
        self.state = state

    def load_events(self):
        return list(self.events)

    def append_event(self, event):
        self.events.append(event)

        return event


def write_events(paths, events):
    paths.state_directory.mkdir(parents=True, exist_ok=True)
    temporary_file = paths.events_file.with_suffix(".tmp")
    temporary_file.write_text("".join(json.dumps(event) + "\n" for event in events))
    temporary_file.replace(paths.events_file)
