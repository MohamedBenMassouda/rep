import datetime
import unittest
import zoneinfo

from rep.app import ANSWER_DONE
from rep.cloud import BUSY_REPORT_FRESH_SECONDS, DESKTOP_COMMAND, DESKTOP_SYNC, NOT_CONFIGURED, Brain, SqlStore
from rep.notifiers.telegram import METHOD_CLEAR_BUTTONS, METHOD_SEND
from rep.progression import RATING_STEADY
from rep.notifiers.telegram import MESSAGE_LIMIT, split_message
from rep.store import EVENT_SESSION, EVENT_SET, EVENT_TEST, new_event
from rep.sync import pack_digest
from tests.helpers import config_with, default_pack_raw, seeded_random, sqlite_execute

OWNER_CHAT = "1001"
STRANGER_CHAT = "2002"
TYPED_REPS = 9
TAPPED_MESSAGE = 55
REPEATED_UPDATE = 500
LONG_LINE_REPEATS = 50
LONG_REPLY_LINES = 60
TIMEZONE = "Africa/Tunis"
MORNING_UTC = datetime.datetime(2026, 11, 18, 10, 0, tzinfo=datetime.timezone.utc)
NO_CHECKS = {"pause_files": [], "check_microphone": False, "check_screen_share": False}
LONG_STREAK_DAYS = 12
ONLY_THE_BUSY_REPORT = 1


def telegram_calls(outcome, method):
    return [call for call in outcome["telegram"] if call["method"] == method]


def unbuildable_app():
    raise AssertionError("the app was built")


def unreadable_history():
    raise AssertionError("the history was read")


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.execute = sqlite_execute(self)
        self.moment = MORNING_UTC

    def brain(self):
        return Brain(SqlStore(self.execute), OWNER_CHAT, clock=lambda: self.moment, chooser=seeded_random())

    def sync_report(self, busy=None, cursor=None):
        pack = default_pack_raw()

        return {"config": config_with(conditions=NO_CHECKS), "pack": pack, "pack_digest": pack_digest(pack),
                "timezone": TIMEZONE, "busy": busy, "cursor": cursor}

    def sync(self, busy=None, cursor=None):
        return self.brain().desktop(DESKTOP_SYNC, {"report": self.sync_report(busy, cursor)})["response"]

    def pending(self):
        return self.brain().store.load_state()["pending"]

    def command(self, *arguments):
        return self.brain().command(list(arguments))

    def next_update(self):
        self.update_id = getattr(self, "update_id", 0) + 1

        return self.update_id

    def tap(self, data, chat=OWNER_CHAT, update_id=None):
        update = {"update_id": update_id or self.next_update(),
                  "callback_query": {"id": "callback", "data": data,
                                     "message": {"message_id": TAPPED_MESSAGE, "chat": {"id": chat}}}}

        return self.brain().telegram(update)

    def send(self, text, chat=OWNER_CHAT):
        return self.brain().telegram({"update_id": self.next_update(), "message": {"text": text, "chat": {"id": chat}}})

    def replies(self, outcome):
        return "\n".join(call["payload"]["text"] for call in telegram_calls(outcome, METHOD_SEND))

    def sessions_logged(self):
        return [event["session"] for event in self.brain().export()["events"] if event["type"] == EVENT_SESSION]

    def test_the_cloud_does_nothing_until_the_desktop_has_sent_its_config(self):
        self.assertEqual(self.brain().tick()["text"], NOT_CONFIGURED)

        self.sync()

        self.assertNotEqual(self.brain().tick()["text"], NOT_CONFIGURED)

    def test_a_challenge_from_the_cloud_waits_in_the_desktop_outbox(self):
        cursor = self.sync()["cursor"]

        self.command("now")

        desktop_cards = self.sync(cursor=cursor)["cards"]
        self.assertEqual(len(desktop_cards), 1)

    def test_a_rating_sent_twice_logs_the_set_once(self):
        self.sync()
        self.command("now")
        token = self.pending()["token"]
        self.command("answer", token, ANSWER_DONE)

        self.command("rate", token, str(RATING_STEADY))
        second = self.command("rate", token, str(RATING_STEADY))

        sets = [event for event in self.brain().export()["events"] if event["type"] == EVENT_SET]
        self.assertEqual(len(sets), 1)
        self.assertTrue(second["text"].startswith("ignored"))

    def test_arguments_that_make_no_sense_are_ignored(self):
        self.sync()

        outcome = self.command("rate", "token", "seven")

        self.assertTrue(outcome["text"].startswith("ignored"))

    def test_a_challenge_goes_to_telegram_with_answer_buttons(self):
        self.sync()

        outcome = self.command("now")

        token = self.pending()["token"]
        sent = telegram_calls(outcome, METHOD_SEND)[0]["payload"]
        callbacks = [button["callback_data"] for button in sent["reply_markup"]["inline_keyboard"][0]]
        self.assertIn(f"answer {token} {ANSWER_DONE}", callbacks)

    def test_tapping_done_on_the_phone_moves_to_the_rating_and_clears_the_tapped_buttons(self):
        self.sync()
        self.command("now")
        token = self.pending()["token"]

        outcome = self.tap(f"answer {token} {ANSWER_DONE}")

        self.assertEqual(self.pending()["stage"], "rate")
        cleared = [call["payload"]["message_id"] for call in telegram_calls(outcome, METHOD_CLEAR_BUTTONS)]
        self.assertIn(TAPPED_MESSAGE, cleared)

    def test_a_number_sent_during_the_rating_becomes_the_reps_done(self):
        self.sync()
        self.command("now")
        token = self.pending()["token"]
        self.tap(f"answer {token} {ANSWER_DONE}")

        self.send(str(TYPED_REPS))
        self.tap(f"rate {token} {RATING_STEADY}")

        sets = [event for event in self.brain().export()["events"] if event["type"] == EVENT_SET]
        self.assertEqual([event["amount"] for event in sets], [TYPED_REPS])

    def test_a_message_from_another_chat_changes_nothing(self):
        self.sync()

        outcome = self.send("/now", chat=STRANGER_CHAT)

        self.assertIsNone(self.pending())
        self.assertEqual(outcome["telegram"], [])

    def test_without_a_linked_chat_the_bot_only_tells_a_stranger_its_chat_id(self):
        self.sync()
        unlinked = Brain(SqlStore(self.execute), None, clock=lambda: self.moment)

        outcome = unlinked.telegram({"message": {"text": "/now", "chat": {"id": STRANGER_CHAT}}})

        self.assertIsNone(self.pending())
        self.assertIn(STRANGER_CHAT, telegram_calls(outcome, METHOD_SEND)[0]["payload"]["text"])

    def test_session_without_a_day_offers_the_training_days_as_buttons(self):
        self.sync()

        outcome = self.send("/session")

        picker = telegram_calls(outcome, METHOD_SEND)[0]["payload"]["reply_markup"]["inline_keyboard"]
        callbacks = [button["callback_data"] for row in picker for button in row]
        self.assertEqual(callbacks, ["session upper", "session legs", "session full"])

    def test_a_training_day_tapped_on_the_phone_is_logged_once_even_if_telegram_sends_it_twice(self):
        self.sync()

        self.tap("session upper", update_id=REPEATED_UPDATE)
        self.tap("session upper", update_id=REPEATED_UPDATE)

        self.assertEqual(self.sessions_logged(), ["upper"])

    def test_session_with_a_day_logs_it_and_an_unknown_day_logs_nothing(self):
        self.sync()

        self.send("/session legs")
        unknown = self.send("/session leg-day")

        self.assertEqual(self.sessions_logged(), ["legs"])
        self.assertIn("unknown session", self.replies(unknown))

    def test_stats_and_today_come_back_as_plain_text(self):
        self.sync()
        self.send("/session upper")

        stats = self.replies(self.send("/stats"))
        today = self.replies(self.send("/today@rep_bot"))

        self.assertIn("Streak", stats)
        self.assertNotIn("\033", stats)
        self.assertIn("Trained: upper", today)

    def test_long_replies_are_split_to_fit_a_telegram_message(self):
        text = "\n".join("line" * LONG_LINE_REPEATS for _ in range(LONG_REPLY_LINES))

        chunks = split_message(text)

        self.assertTrue(all(len(chunk) <= MESSAGE_LIMIT for chunk in chunks))
        self.assertEqual("\n".join(chunks), text)

    def test_a_fresh_busy_report_holds_challenges_back_and_a_stale_one_does_not(self):
        self.sync()

        while not self.brain().store.load_state()["next_due"]:
            self.brain().tick()

        self.moment = datetime.datetime.fromtimestamp(self.brain().store.load_state()["next_due"], datetime.timezone.utc)
        self.sync(busy="microphone in use")

        self.assertEqual(self.brain().tick()["text"], "microphone in use")

        self.moment += datetime.timedelta(seconds=BUSY_REPORT_FRESH_SECONDS)
        self.assertNotEqual(self.brain().tick()["text"], "microphone in use")

    def test_a_tick_with_nothing_due_does_not_read_the_history(self):
        self.sync()
        brain = self.brain()
        state = brain.store.load_state()
        state["last_test_day"] = self.moment.date().isoformat()
        state["next_due"] = (self.moment + datetime.timedelta(hours=1)).timestamp()
        brain.store.save_state(state)
        brain.store.load_events = unreadable_history

        self.assertEqual(brain.tick()["text"], "nothing due")

    def logged_sets(self, days_back, sets_per_day):
        today = self.moment.astimezone(zoneinfo.ZoneInfo(TIMEZONE)).replace(tzinfo=None)

        for days in range(days_back):
            for _ in range(sets_per_day):
                self.brain().store.append_event(new_event(EVENT_SET, now=today - datetime.timedelta(days=days),
                                                          kind="hard", group="push", exercise="clap_push_up"))

    def test_the_streak_counts_days_older_than_the_recent_history_the_cloud_loads(self):
        self.sync()
        minimum = config_with()["training"]["streak_minimum"]
        self.logged_sets(LONG_STREAK_DAYS, minimum)

        self.assertEqual(self.brain().build_app().today()["streak"], LONG_STREAK_DAYS)

    def test_the_cloud_app_sees_recent_sets_and_every_test_but_not_old_sets(self):
        self.sync()
        long_ago = self.moment.replace(tzinfo=None) - datetime.timedelta(days=LONG_STREAK_DAYS)
        self.brain().store.append_event(new_event(EVENT_SET, now=long_ago, kind="hard", group="push"))
        self.brain().store.append_event(new_event(EVENT_TEST, now=long_ago, results={}))
        self.logged_sets(1, 1)

        types = sorted(event["type"] for event in self.brain().build_app().events)

        self.assertEqual(types, [EVENT_SET, EVENT_TEST])

    def test_a_sync_with_an_unchanged_config_only_rewrites_the_busy_report(self):
        self.sync()
        self.moment += datetime.timedelta(minutes=1)
        writes = []
        recording = lambda statement, *parameters: (writes.append(statement) if statement.startswith(
            "INSERT INTO settings") else None) or self.execute(statement, *parameters)
        store = SqlStore(recording)
        Brain(store, clock=lambda: self.moment).desktop(DESKTOP_SYNC, {"report": self.sync_report()})

        self.assertEqual(len(writes), ONLY_THE_BUSY_REPORT)

    def test_todays_numbers_are_reused_until_something_changes(self):
        self.sync()
        brain = self.brain()
        brain.build_app = unbuildable_app

        brain.desktop(DESKTOP_SYNC, {"report": self.sync_report()})

        self.command("session", "upper")
        self.assertEqual(self.sync()["today"]["trained"], ["upper"])

    def test_importing_the_same_backup_twice_adds_nothing(self):
        self.sync()
        self.brain().command(["now"])
        backup = self.brain().export()
        target = Brain(SqlStore(sqlite_execute(self)))

        first = target.import_backup(backup)
        second = target.import_backup(backup)

        self.assertEqual(first["added"], len(backup["events"]))
        self.assertEqual(second["added"], 0)


if __name__ == "__main__":
    unittest.main()
