import datetime
import functools
import hashlib
import json
import random
import zoneinfo

from rep.ai import model_configured
from rep.app import ANSWER_SKIP, ANSWERS, MEETING_PAUSE_MINUTES, STAGE_RATE, STATUS_NOTED, App
from rep.assistant import (NOTE_DONE, NOTE_SKIP, coach_reply, coach_request, note_answer, note_request, pain_answer,
                           pain_request)
from rep.catalog import parse_pack
from rep.notifiers import Card, OutboxNotifier, card_to_dict
from rep.charts import phone_stats_text
from rep.maxtest import (QUESTION_RESULT, TEST_INSTRUCTIONS, result_question, skill_options, skill_question, skill_step,
                         test_questions)
from rep.notifiers.telegram import (CALLBACK_SEPARATOR, MESSAGE_LIMIT, ONE_PER_ROW, PHONE_COMMANDS, TEST_CALLBACKS,
                                    TEST_START, acknowledge, callback_arguments, clear_buttons, phone_buttons, picker,
                                    routine_text, send_card, send_long_text, send_text, session_picker, step_picker,
                                    today_text)
from rep.routine import describe_sessions
from rep.progression import RATINGS
from rep.store import EVENT_SET, EVENT_TEST, empty_state

SETTING_STATE = "state"
SETTING_CONFIG = "config"
SETTING_PACK = "pack"
SETTING_TIMEZONE = "timezone"
SETTING_PACK_DIGEST = "pack_digest"
SETTING_TODAY = "today"
SETTING_OPEN_MESSAGE = "open_message"
SETTING_LAST_UPDATE = "last_telegram_update"
SETTING_MAX_TEST = "max_test"
TEST_SESSION_SECONDS = 7200
MAXIMUM_TEST_RESULT = 999
DEFAULT_TIMEZONE = "UTC"
RECENT_HISTORY_DAYS = 7
CARD_KEEP_SECONDS = 86400
COMMAND_ANSWER = "answer"
COMMAND_RATE = "rate"
COMMAND_SESSION = "session"
COMMAND_NOW = "now"
COMMAND_SUMMARY = "summary"
COMMAND_DISMISS = "dismiss"
COMMAND_PAUSE = "pause"
COMMAND_AWAY = "away"
COMMAND_REST = "rest"
COMMAND_APPLY_TEST = "apply-test"
TELEGRAM_NOW = "/now"
TELEGRAM_SESSION = "/session"
TELEGRAM_TODAY = "/today"
TELEGRAM_STATS = "/stats"
TELEGRAM_ROUTINE = "/routine"
TELEGRAM_SUMMARY = "/summary"
TELEGRAM_TEST = "/test"
TELEGRAM_PAUSE = "/pause"
TELEGRAM_AWAY = "/away"
TELEGRAM_COACH = "/coach"
TELEGRAM_PAIN = "/pain"
PURPOSE_COACH = "coach"
PURPOSE_NOTE = "note"
PURPOSE_PAIN = "pain"
TELEGRAM_SKIP = "/skip"
TELEGRAM_CANCEL = "/cancel"
TELEGRAM_HELP_COMMANDS = ("/help", "/start")
TELEGRAM_BOT_SUFFIX = "@"
TELEGRAM_COMMAND_PREFIX = "/"
DESKTOP_SYNC = "sync"
DESKTOP_COMMAND = "command"
DESKTOP_EXPORT = "export"
DESKTOP_IMPORT = "import"
STATUS_SHOWN = "shown"
STATUS_DISMISSED = "dismissed"
STATUS_IGNORED = "ignored"
STATUS_UNKNOWN_CHAT = "unknown chat"
STATUS_HELP = "help"
STATUS_NOTHING_TO_RATE = "nothing to rate"
STATUS_TYPED = "typed"
STATUS_DUPLICATE = "duplicate update"
STATUS_ANSWERED = "answered"
STATUS_TESTING = "max test in progress"
STATUS_ASKING = "asking the model"
ANSWER_ARGUMENT_COUNT = 3
AWAY_ARGUMENT_COUNT = 3
BARE_COMMAND_ARGUMENT_COUNT = 1
REST_ARGUMENT_COUNT = 3
SINGLE_VALUE_ARGUMENT_COUNT = 2
NO_LINE_COMMAND = ""
REQUIRED_EVENT_FIELDS = {"id", "type", "day"}
NOT_CONFIGURED = "not set up yet: run `rep tick` on your desktop once"
IGNORED_ARGUMENTS = "ignored: those arguments don't make sense"
NOTHING_TO_RATE = "No set is waiting for a rating right now."
TYPED_REPS_REPLY = "Got {done}. Now tap how it felt on the card above."
TELEGRAM_HELP = "\n".join((
    "rep sends your challenge cards here. Tap the buttons to answer them; while a set waits for its rating, "
    "send the reps you did as a number first.",
    "",
    "/now: a challenge right now",
    "/session: log a training day (or /session chest-day)",
    "/today: today's sets, streak and skills",
    "/stats: targets, ladders and the week's caps",
    "/routine: your training days and their muscles",
    "/summary: today's summary",
    "/test: the max test, one question at a time (/skip, /cancel)",
    "/coach: a review of your week and what to change",
    "/pain: say what hurts (/pain left shoulder) and get advice and rest options",
    "While a card waits, you can also write what you did: did 12, 2 left; or: skip, my wrist hurts.",
    f"/pause: no challenges for {MEETING_PAUSE_MINUTES} minutes (or /pause 90; /pause 0 resumes)",
    "/away: your away days; /away tomorrow 14 stops challenges at 14:00 that day (/away friday home undoes it)",
    "",
    "Export and import stay on your desktop: rep export, rep import.",
))
AI_NOT_SET_UP = ("No AI model is set up: fill [ai] url and model in your desktop config, run rep tick, "
                 "and set AI_KEY on the rep Worker.")
NOTE_NOT_UNDERSTOOD = "I didn't get that. Tap the card, or write something like: did 12, 2 left."
NOTE_SKIPPED = "Skipped."
PAIN_NO_ANSWER = "No advice came back. Try again in a minute, or rest that area with /pause."
PAIN_NEEDS_TEXT = "Say what hurts, like: /pain left shoulder when I push."
NO_REST_LABEL = "Keep going"
TEST_INTRO = f"{TEST_INSTRUCTIONS} Send each result as a number, /skip to leave one out, /cancel to stop."
TEST_CANCELLED = "Max test stopped. Nothing was saved."
TEST_NOT_RUNNING = "No max test is running: /test starts one."
TEST_EMPTY = "This exercise pack has no max test."
TEST_BAD_RESULT = f"Send a number up to {MAXIMUM_TEST_RESULT}, /skip or /cancel."
TEST_BAD_STEP = "Pick one of the buttons, send its number, /skip or /cancel."
TELEGRAM_UNKNOWN_CHAT = "This chat isn't linked to rep. Its chat id is {chat_id}: set it as TELEGRAM_CHAT_ID."
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
        text = json.dumps(value)

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

    def last_event_row(self):
        return self.execute("SELECT COALESCE(MAX(rowid), 0) AS last FROM events")[0]["last"]

    def last_card_sequence(self):
        return self.execute("SELECT COALESCE(MAX(sequence), 0) AS last FROM cards")[0]["last"]

    def cards_after(self, sequence):
        rows = self.execute("SELECT sequence, time, body FROM cards WHERE sequence > ? ORDER BY sequence", sequence)

        return [{"sequence": row["sequence"], "time": row["time"], "card": json.loads(row["body"])} for row in rows]


@functools.lru_cache(maxsize=1)
def pack_from_text(text):
    return parse_pack(json.loads(text))


def empty_outcome(text):
    return {"text": text, "telegram": [], "cards": [], "model": None}


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
    def __init__(self, store, chat_id=None, clock=None, chooser=None, can_ask_model=False):
        self.store, self.chat_id, self.can_ask_model = store, str(chat_id or ""), can_ask_model
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
        return STATUS_TESTING if self.test_session() else None

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

            if phone_buttons(card):
                outcome["telegram"] += self.clear_open_message()

            if self.chat_id:
                outcome["telegram"].append(send_card(self.chat_id, card))

        return outcome

    def clear_open_message(self):
        open_message = self.store.setting(SETTING_OPEN_MESSAGE)

        if not open_message:
            return []

        self.store.put_setting(SETTING_OPEN_MESSAGE, None)

        return [clear_buttons(self.chat_id, open_message)]

    def remember_message(self, message_id):
        self.store.put_setting(SETTING_OPEN_MESSAGE, message_id)

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
        elif name == COMMAND_SESSION and len(arguments) >= SINGLE_VALUE_ARGUMENT_COUNT:
            text = app.log_session(CALLBACK_SEPARATOR.join(arguments[1:]))
        elif name == COMMAND_NOW:
            text = app.now()
        elif name == COMMAND_SUMMARY:
            app.notifier.show(Card(*app.summary_lines()))
            text = STATUS_SHOWN
        elif name == COMMAND_PAUSE and len(arguments) == SINGLE_VALUE_ARGUMENT_COUNT and arguments[1].isdigit():
            text = app.pause(int(arguments[1]))
        elif name == COMMAND_AWAY and len(arguments) == AWAY_ARGUMENT_COUNT:
            text = app.away(arguments[1], arguments[2])
        elif name == COMMAND_AWAY and len(arguments) == BARE_COMMAND_ARGUMENT_COUNT:
            text = app.away_plan()
        elif name == COMMAND_REST and len(arguments) == REST_ARGUMENT_COUNT and arguments[2].isdigit():
            text = app.rest(arguments[1], int(arguments[2]))
        elif name == COMMAND_DISMISS:
            text = STATUS_DISMISSED
        elif name == COMMAND_APPLY_TEST and len(arguments) == SINGLE_VALUE_ARGUMENT_COUNT:
            test = json.loads(arguments[1])
            text = app.apply_test(test["results"], test["skill_steps"])
        else:
            text = IGNORED_ARGUMENTS

        return self.finish(app, text)

    def receive_report(self, report):
        if "pack" in report:
            self.store.put_setting(SETTING_PACK, report["pack"])
            self.store.put_setting(SETTING_PACK_DIGEST, report["pack_digest"])

        self.store.put_setting(SETTING_CONFIG, report["config"])
        self.store.put_setting(SETTING_TIMEZONE, report["timezone"])
        self.zone = None

        return self.store.setting(SETTING_PACK_DIGEST) == report["pack_digest"]

    def today_marker(self):
        parts = (self.store.setting_text(SETTING_STATE) or "", self.store.setting_text(SETTING_CONFIG) or "",
                 self.local_now().date().isoformat(), str(self.store.last_event_row()))

        return hashlib.sha256("\n".join(parts).encode()).hexdigest()

    def today(self):
        marker = self.today_marker()
        cached = self.store.setting(SETTING_TODAY)

        if cached and cached["marker"] == marker:
            return cached["today"]

        today = self.build_app().today()
        self.store.put_setting(SETTING_TODAY, {"marker": marker, "today": today})

        return today

    def catch_up(self, cursor):
        pending = self.store.load_state()["pending"]

        return {
            "cards": self.store.cards_after(cursor) if cursor is not None else [],
            "cursor": self.store.last_card_sequence(),
            "pending": {"token": pending["token"], "stage": pending["stage"]} if pending else None,
            "today": self.today(),
        }

    def desktop(self, action, body):
        if action in (DESKTOP_SYNC, DESKTOP_COMMAND) and not self.receive_report(body["report"]):
            return {"response": {"needs_pack": True}, "telegram": []}

        if action == DESKTOP_SYNC:
            return {"response": self.catch_up(body["report"].get("cursor")), "telegram": []}

        if action == DESKTOP_COMMAND:
            outcome = self.command(body.get("arguments", []))
            response = {"text": outcome["text"], **self.catch_up(body["report"].get("cursor"))}

            return {"response": response, "telegram": outcome["telegram"]}

        if action == DESKTOP_EXPORT:
            return {"response": self.export(), "telegram": []}

        if action == DESKTOP_IMPORT:
            return {"response": self.import_backup(body), "telegram": []}

        return {"response": {"error": f"unknown action {action!r}"}, "telegram": []}

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

    def telegram(self, update):
        callback = update.get("callback_query")
        message = callback["message"] if callback else update.get("message")

        if not message:
            return empty_outcome(STATUS_IGNORED)

        chat_id = str(message["chat"]["id"])

        if chat_id != self.chat_id:
            return {**empty_outcome(STATUS_UNKNOWN_CHAT), "telegram": [send_text(chat_id, TELEGRAM_UNKNOWN_CHAT.format(
                chat_id=chat_id))] if not self.chat_id else []}

        if self.already_handled(update.get("update_id")):
            return empty_outcome(STATUS_DUPLICATE)

        if callback:
            return self.telegram_button(callback)

        return self.telegram_text(message.get("text", "").strip())

    def telegram_button(self, callback):
        arguments = callback_arguments(callback.get("data", ""))
        message_id = callback["message"]["message_id"]

        if self.store.setting(SETTING_OPEN_MESSAGE) == message_id:
            self.store.put_setting(SETTING_OPEN_MESSAGE, None)

        if arguments[0] in TEST_CALLBACKS:
            outcome = self.start_test() if arguments[0] == TEST_START else self.answer_test(arguments[-1])
        elif arguments[0] in PHONE_COMMANDS:
            outcome = self.command(arguments)
        else:
            outcome = empty_outcome(IGNORED_ARGUMENTS)

        outcome["telegram"] = [acknowledge(callback["id"], outcome["text"]),
                               clear_buttons(self.chat_id, message_id)] + outcome["telegram"]

        return outcome

    def already_handled(self, update_id):
        if not isinstance(update_id, int):
            return False

        if update_id <= (self.store.setting(SETTING_LAST_UPDATE) or 0):
            return True

        self.store.put_setting(SETTING_LAST_UPDATE, update_id)

        return False

    def reply(self, status, text):
        return {**empty_outcome(status), "telegram": send_long_text(self.chat_id, text)}

    def telegram_text(self, text):
        command, _, argument = text.partition(CALLBACK_SEPARATOR)
        command = command.split(TELEGRAM_BOT_SUFFIX, 1)[0].lower()

        if command in (TELEGRAM_SKIP, TELEGRAM_CANCEL) or (text.isdigit() and self.test_session()):
            return self.test_reply(command, text)

        if text.isdigit():
            return self.typed_reps(int(text))

        if command == TELEGRAM_TEST:
            return self.start_test()

        if text and not command.startswith(TELEGRAM_COMMAND_PREFIX) and self.model_ready() and self.pending():
            return self.ask_about_note(text)

        if command in TELEGRAM_HELP_COMMANDS or not command.startswith(TELEGRAM_COMMAND_PREFIX):
            return self.reply(STATUS_HELP, TELEGRAM_HELP)

        if not self.configured():
            return self.reply(NOT_CONFIGURED, NOT_CONFIGURED)

        if command in (TELEGRAM_COACH, TELEGRAM_PAIN) and not self.model_ready():
            return self.reply(STATUS_HELP, AI_NOT_SET_UP)

        if command == TELEGRAM_COACH:
            return self.model_call(PURPOSE_COACH, coach_request(self.build_app()), {})

        if command == TELEGRAM_PAIN:
            return self.ask_about_pain(argument.strip())

        if command == TELEGRAM_NOW:
            return self.command([COMMAND_NOW])

        if command == TELEGRAM_SESSION:
            return self.telegram_session(argument.strip())

        if command == TELEGRAM_PAUSE:
            minutes = argument.strip() or str(MEETING_PAUSE_MINUTES)
            outcome = self.command([COMMAND_PAUSE, minutes])

            return self.reply(outcome["text"], outcome["text"])

        if command == TELEGRAM_AWAY:
            outcome = self.command([COMMAND_AWAY] + argument.split())

            return self.reply(outcome["text"], outcome["text"])

        return self.telegram_report(command)

    def model_ready(self):
        settings = (self.store.setting(SETTING_CONFIG) or {}).get("ai")

        return self.can_ask_model and self.configured() and bool(settings) and model_configured(settings)

    def pending(self):
        return self.store.load_state()["pending"]

    def model_call(self, purpose, request, context):
        return {**empty_outcome(STATUS_ASKING), "model": {"purpose": purpose, "request": request, "context": context}}

    def ask_about_note(self, note):
        app = self.build_app()
        pending = app.state["pending"]

        return self.model_call(PURPOSE_NOTE, note_request(app, note), {"token": pending["token"],
                                                                       "kind": pending["kind"]})

    def ask_about_pain(self, note):
        if not note:
            return self.reply(STATUS_HELP, PAIN_NEEDS_TEXT)

        return self.model_call(PURPOSE_PAIN, pain_request(self.build_app(), note), {})

    def model_answered(self, call, response):
        purpose, context = call["purpose"], call["context"]

        if purpose == PURPOSE_COACH:
            return self.reply(STATUS_ANSWERED, coach_reply(response))

        if purpose == PURPOSE_NOTE:
            return self.apply_note(note_answer(response, context["kind"]), context["token"])

        if purpose == PURPOSE_PAIN:
            return self.offer_rest(pain_answer(response, pack_from_text(self.store.setting_text(SETTING_PACK))))

        return empty_outcome(IGNORED_ARGUMENTS)

    def apply_note(self, note, token):
        if note is None or note["answer"] not in (NOTE_DONE, NOTE_SKIP):
            return self.reply(STATUS_HELP, NOTE_NOT_UNDERSTOOD)

        app = self.build_app()

        if note["answer"] == NOTE_SKIP:
            text = app.answer(token, ANSWER_SKIP)
        elif note["rating"] is None:
            text = app.note_reps(token, note["reps"])
        else:
            text = app.log_set(token, note["rating"], note["reps"])

        cleared = self.clear_open_message() if app.state["pending"] is None else []
        outcome = self.finish(app, text)
        replies = {ANSWER_SKIP: NOTE_SKIPPED, STATUS_NOTED: TYPED_REPS_REPLY.format(done=note["reps"])}
        reply = send_long_text(self.chat_id, replies.get(text, text))

        return {**outcome, "telegram": cleared + (outcome["telegram"] or reply)}

    def offer_rest(self, advice):
        if advice is None:
            return self.reply(STATUS_HELP, PAIN_NO_ANSWER)

        if not advice["rest"]:
            return self.reply(STATUS_ANSWERED, advice["advice"])

        choices = [(f"Rest {group} {advice['days']} d", CALLBACK_SEPARATOR.join((COMMAND_REST, group,
                                                                                   str(advice["days"]))))
                   for group in advice["rest"]] + [(NO_REST_LABEL, COMMAND_DISMISS)]

        return {**empty_outcome(STATUS_ANSWERED), "telegram": [picker(self.chat_id, advice["advice"][:MESSAGE_LIMIT], choices,
                                                                      ONE_PER_ROW)]}

    def telegram_session(self, session):
        if session:
            outcome = self.command([COMMAND_SESSION, session])

            return outcome if outcome["telegram"] else self.reply(outcome["text"], outcome["text"])

        allowances = self.build_app().config["training"]["session_allowances"]

        return {**empty_outcome(STATUS_HELP), "telegram": [session_picker(self.chat_id, list(allowances))]}

    def telegram_report(self, command):
        app = self.build_app()
        training = app.config["training"]

        if command == TELEGRAM_TODAY:
            return self.reply(STATUS_ANSWERED, today_text(self.today()))

        if command == TELEGRAM_STATS:
            return self.reply(STATUS_ANSWERED, phone_stats_text(app))

        if command == TELEGRAM_ROUTINE:
            return self.reply(STATUS_ANSWERED, routine_text(describe_sessions(training, training["session_allowances"])))

        if command == TELEGRAM_SUMMARY:
            return self.reply(STATUS_ANSWERED, "\n".join(app.summary_lines()))

        return self.reply(STATUS_HELP, TELEGRAM_HELP)

    def typed_reps(self, done):
        if not self.configured():
            return empty_outcome(NOT_CONFIGURED)

        app = self.build_app()
        pending = app.state["pending"]

        if not pending or pending["stage"] != STAGE_RATE:
            return self.reply(STATUS_NOTHING_TO_RATE, NOTHING_TO_RATE)

        pending["typed"] = done
        app.save()

        return self.reply(STATUS_TYPED, TYPED_REPS_REPLY.format(done=done))

    def test_session(self):
        session = self.store.setting(SETTING_MAX_TEST)

        if session and self.now_seconds() - session["started"] < TEST_SESSION_SECONDS:
            return session

        return None

    def test_reply(self, command, text):
        if not self.test_session():
            return self.reply(STATUS_HELP, TEST_NOT_RUNNING)

        if command == TELEGRAM_CANCEL:
            self.store.put_setting(SETTING_MAX_TEST, None)

            return self.reply(STATUS_ANSWERED, TEST_CANCELLED)

        return self.answer_test(None if command == TELEGRAM_SKIP else text)

    def test_plan(self):
        app = self.build_app()

        return app, test_questions(app.pack, app.config["profile"]["skills"])

    def ask_test_question(self, app, questions, position):
        kind, identifier = questions[position]
        counter = f"{position + 1}/{len(questions)} · "

        if kind == QUESTION_RESULT:
            return [send_text(self.chat_id, f"{counter}{result_question(app.pack.exercises[identifier])}?")]

        ladder = app.pack.skills[identifier]

        return [step_picker(self.chat_id, counter + skill_question(ladder), skill_options(app.pack, ladder))]

    def start_test(self):
        if not self.configured():
            return self.reply(NOT_CONFIGURED, NOT_CONFIGURED)

        app, questions = self.test_plan()

        if not questions:
            return self.reply(STATUS_HELP, TEST_EMPTY)

        self.store.put_setting(SETTING_MAX_TEST, {"started": self.now_seconds(), "position": 0, "results": {},
                                                  "skill_steps": {}})
        questions_text = self.ask_test_question(app, questions, 0)

        return {**empty_outcome(STATUS_TESTING), "telegram": [send_text(self.chat_id, TEST_INTRO)] + questions_text}

    def answer_test(self, answer):
        session = self.test_session()

        if not session:
            return self.reply(STATUS_HELP, TEST_NOT_RUNNING)

        app, questions = self.test_plan()
        position = session["position"]

        if position < len(questions):
            kind, identifier = questions[position]

            if kind == QUESTION_RESULT and answer is not None:

                if not answer.isdigit() or int(answer) > MAXIMUM_TEST_RESULT:
                    return self.reply(STATUS_TESTING, TEST_BAD_RESULT)

                session["results"][identifier] = int(answer)
            elif kind != QUESTION_RESULT:
                step = 0 if answer is None else skill_step(answer, app.pack.skills[identifier])

                if step is None:
                    return self.reply(STATUS_TESTING, TEST_BAD_STEP)

                session["skill_steps"][identifier] = step

        session["position"] = position + 1

        if session["position"] < len(questions):
            self.store.put_setting(SETTING_MAX_TEST, session)

            return {**empty_outcome(STATUS_TESTING), "telegram": self.ask_test_question(app, questions,
                                                                                         session["position"])}

        return self.finish_test(session)

    def finish_test(self, session):
        self.store.put_setting(SETTING_MAX_TEST, None)
        test = json.dumps({"results": session["results"], "skill_steps": session["skill_steps"]})
        outcome = self.command([COMMAND_APPLY_TEST, test])
        summary = f"{outcome['text']}\n\n{phone_stats_text(self.build_app())}"

        return {**outcome, "telegram": outcome["telegram"] + send_long_text(self.chat_id, summary)}
