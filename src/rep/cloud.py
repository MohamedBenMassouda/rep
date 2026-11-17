import datetime
import functools
import json
import random
import zoneinfo

from rep.app import ANSWERS, App
from rep.catalog import parse_pack
from rep.notifiers import Card, OutboxNotifier, card_to_dict
from rep.progression import RATINGS
from rep.store import EVENT_SET, EVENT_TEST, empty_state

SETTING_STATE = "state"
SETTING_CONFIG = "config"
SETTING_PACK = "pack"
SETTING_TIMEZONE = "timezone"
SETTING_BUSY = "busy"
DEFAULT_TIMEZONE = "UTC"
BUSY_REPORT_FRESH_SECONDS = 600
RECENT_HISTORY_DAYS = 7
CARD_KEEP_SECONDS = 86400
COMMAND_ANSWER = "answer"
COMMAND_RATE = "rate"
COMMAND_SESSION = "session"
COMMAND_NOW = "now"
COMMAND_SUMMARY = "summary"
COMMAND_DISMISS = "dismiss"
COMMAND_APPLY_TEST = "apply-test"
DESKTOP_SYNC = "sync"
DESKTOP_COMMAND = "command"
DESKTOP_EXPORT = "export"
DESKTOP_IMPORT = "import"
STATUS_SHOWN = "shown"
STATUS_DISMISSED = "dismissed"
ANSWER_ARGUMENT_COUNT = 3
SINGLE_VALUE_ARGUMENT_COUNT = 2
NO_LINE_COMMAND = ""
REQUIRED_EVENT_FIELDS = {"id", "type", "day"}
NOT_CONFIGURED = "not set up yet: run `rep tick` on your desktop once"
IGNORED_ARGUMENTS = "ignored: those arguments don't make sense"
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, type TEXT NOT NULL, day TEXT NOT NULL,"
    " time INTEGER NOT NULL, body TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cards (sequence INTEGER PRIMARY KEY AUTOINCREMENT, time INTEGER NOT NULL,"
    " body TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS events_by_day ON events (day)",
    "CREATE INDEX IF NOT EXISTS events_by_type_and_day ON events (type, day)",
    "CREATE INDEX IF NOT EXISTS cards_by_time ON cards (time)",
)


class SqlStore:
    def __init__(self, execute):
        self.execute = execute
        self.history_start = None

        for statement in SCHEMA:
            execute(statement)

        self.setting_texts = {row["key"]: row["value"] for row in execute("SELECT key, value FROM settings")}

    def setting_text(self, key):
        return self.setting_texts.get(key)

    def setting(self, key):
        text = self.setting_text(key)

        return json.loads(text) if text is not None else None

    def put_setting(self, key, value):
        text = json.dumps(value, sort_keys=True)

        if self.setting_texts.get(key) == text:
            return

        self.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", key, text)
        self.setting_texts[key] = text

    def load_state(self):
        state = empty_state()
        state.update({key: value for key, value in (self.setting(SETTING_STATE) or {}).items() if key in state})

        return state

    def save_state(self, state):
        self.put_setting(SETTING_STATE, state)

    def load_events(self):
        if self.history_start is None:
            return self.all_events()

        rows = self.execute("SELECT body FROM events WHERE day >= ? OR type = ? ORDER BY time",
                            self.history_start, EVENT_TEST)

        return [json.loads(row["body"]) for row in rows]

    def all_events(self):
        return [json.loads(row["body"]) for row in self.execute("SELECT body FROM events ORDER BY time")]

    def completed_counts(self):
        rows = self.execute("SELECT day, COUNT(*) AS total FROM events WHERE type = ? GROUP BY day", EVENT_SET)

        return {row["day"]: row["total"] for row in rows}

    def append_event(self, event):
        self.execute("INSERT OR IGNORE INTO events (id, type, day, time, body) VALUES (?, ?, ?, ?, ?)",
                     event["id"], event["type"], event["day"], event.get("time", 0), json.dumps(event))

        return event

    def event_count(self):
        return self.execute("SELECT COUNT(*) AS total FROM events")[0]["total"]

    def add_card(self, card, now_seconds):
        self.execute("DELETE FROM cards WHERE time < ?", now_seconds - CARD_KEEP_SECONDS)
        self.execute("INSERT INTO cards (time, body) VALUES (?, ?)", now_seconds, json.dumps(card_to_dict(card)))

        return self.last_card_sequence()

    def last_card_sequence(self):
        return self.execute("SELECT COALESCE(MAX(sequence), 0) AS last FROM cards")[0]["last"]

    def cards_after(self, sequence):
        rows = self.execute("SELECT sequence, time, body FROM cards WHERE sequence > ? ORDER BY sequence", sequence)

        return [{"sequence": row["sequence"], "time": row["time"], "card": json.loads(row["body"])} for row in rows]


@functools.lru_cache(maxsize=1)
def pack_from_text(text):
    return parse_pack(json.loads(text))


def empty_outcome(text):
    return {"text": text, "cards": []}


def parsed_rate_arguments(arguments):
    try:
        rating = int(arguments[2])
        done = int(arguments[3]) if len(arguments) > 3 else None
    except (IndexError, ValueError):
        return None

    if rating not in RATINGS or (done is not None and done < 0):
        return None

    return rating, done


class Brain:
    def __init__(self, store, clock=None, chooser=None):
        self.store = store
        self.clock = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))
        self.chooser = chooser or random.Random()
        self.zone = None

    def configured(self):
        return self.store.setting_text(SETTING_CONFIG) is not None and self.store.setting_text(SETTING_PACK) is not None

    def local_now(self):
        if self.zone is None:
            self.zone = zoneinfo.ZoneInfo(self.store.setting(SETTING_TIMEZONE) or DEFAULT_TIMEZONE)

        return self.clock().astimezone(self.zone)

    def now_seconds(self):
        return int(self.clock().timestamp())

    def busy_reason(self):
        report = self.store.setting(SETTING_BUSY)

        if report and self.now_seconds() - report["time"] < BUSY_REPORT_FRESH_SECONDS:
            return report["reason"]

        return None

    def build_app(self):
        config = self.store.setting(SETTING_CONFIG)
        config["display"]["line_command"] = NO_LINE_COMMAND
        self.store.history_start = (self.local_now().date() - datetime.timedelta(days=RECENT_HISTORY_DAYS)).isoformat()

        return App(self.store, config, pack_from_text(self.store.setting_text(SETTING_PACK)), OutboxNotifier(), self.chooser,
                   clock=self.local_now, busy_check=self.busy_reason)

    def finish(self, app, text):
        outcome = empty_outcome(text)

        for card in app.notifier.cards:
            sequence = self.store.add_card(card, self.now_seconds())
            outcome["cards"].append({"sequence": sequence, "time": self.now_seconds(), "card": card_to_dict(card)})

        return outcome

    def tick(self):
        if not self.configured():
            return empty_outcome(NOT_CONFIGURED)

        app = self.build_app()

        return self.finish(app, app.tick())

    def command(self, arguments):
        if not self.configured():
            return empty_outcome(NOT_CONFIGURED)

        if not arguments:
            return empty_outcome(IGNORED_ARGUMENTS)

        app = self.build_app()
        name = arguments[0]
        rate_arguments = parsed_rate_arguments(arguments) if name == COMMAND_RATE else None

        if name == COMMAND_ANSWER and len(arguments) == ANSWER_ARGUMENT_COUNT and arguments[2] in ANSWERS:
            text = app.answer(arguments[1], arguments[2])
        elif name == COMMAND_RATE and rate_arguments:
            text = app.rate(arguments[1], *rate_arguments)
        elif name == COMMAND_SESSION and len(arguments) == SINGLE_VALUE_ARGUMENT_COUNT:
            text = app.log_session(arguments[1])
        elif name == COMMAND_NOW:
            text = app.now()
        elif name == COMMAND_SUMMARY:
            app.notifier.show(Card(*app.summary_lines()))
            text = STATUS_SHOWN
        elif name == COMMAND_DISMISS:
            text = STATUS_DISMISSED
        elif name == COMMAND_APPLY_TEST and len(arguments) == SINGLE_VALUE_ARGUMENT_COUNT:
            test = json.loads(arguments[1])
            text = app.apply_test(test["results"], test["skill_steps"])
        else:
            text = IGNORED_ARGUMENTS

        return self.finish(app, text)

    def receive_report(self, report):
        self.store.put_setting(SETTING_CONFIG, report["config"])
        self.store.put_setting(SETTING_PACK, report["pack"])
        self.store.put_setting(SETTING_TIMEZONE, report["timezone"])
        self.store.put_setting(SETTING_BUSY, {"reason": report["busy"], "time": self.now_seconds()})
        self.zone = None

    def catch_up(self, cursor):
        cards = self.store.cards_after(cursor) if cursor is not None else []
        app = self.build_app()
        pending = app.state["pending"]

        return {
            "cards": cards,
            "cursor": self.store.last_card_sequence(),
            "pending": {"token": pending["token"], "stage": pending["stage"]} if pending else None,
            "today": app.today(),
        }

    def desktop_sync(self, report):
        self.receive_report(report)

        return self.catch_up(report.get("cursor"))

    def desktop(self, action, body):
        if action == DESKTOP_SYNC:
            return self.desktop_sync(body)

        if action == DESKTOP_COMMAND:
            self.receive_report(body["report"])
            outcome = self.command(body.get("arguments", []))

            return {"text": outcome["text"], **self.catch_up(body["report"].get("cursor"))}

        if action == DESKTOP_EXPORT:
            return self.export()

        if action == DESKTOP_IMPORT:
            return self.import_backup(body)

        return {"error": f"unknown action {action!r}"}

    def export(self):
        return {"state": self.store.load_state(), "events": self.store.all_events()}

    def import_backup(self, backup):
        before = self.store.event_count()

        for event in backup.get("events", []):

            if REQUIRED_EVENT_FIELDS <= event.keys():
                self.store.append_event(event)

        if backup.get("state"):
            self.store.save_state(backup["state"])

        return {"added": self.store.event_count() - before}
