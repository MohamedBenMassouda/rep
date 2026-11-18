import datetime
import unittest
import zoneinfo

from rep.app import ANSWER_DONE, MEETING_PAUSE_MINUTES
from rep.cloud import (AI_NOT_SET_UP, DESKTOP_COMMAND, DESKTOP_SYNC, MAXIMUM_TEST_RESULT, NOT_CONFIGURED,
                       NOTE_NOT_UNDERSTOOD, PURPOSE_COACH, PURPOSE_NOTE, STATUS_TESTING, TEST_NOT_RUNNING, TEST_SESSION_SECONDS, Brain, SqlStore)
from rep.notifiers.telegram import METHOD_CLEAR_BUTTONS, METHOD_SEND
from rep.progression import RATING_STEADY
from rep.notifiers.telegram import MESSAGE_LIMIT, TEST_START, split_message
from rep.store import EVENT_SESSION, EVENT_SET, EVENT_TEST, new_event
from rep.sync import pack_digest
from rep.config import DEFAULTS
from tests.helpers import config_with, default_pack_raw, model_json, model_response, seeded_random, sqlite_execute

OWNER_CHAT = "1001"
STRANGER_CHAT = "2002"
TYPED_REPS = 9
TAPPED_MESSAGE = 55
REPEATED_UPDATE = 500
LONG_LINE_REPEATS = 50
LONG_REPLY_LINES = 60
TESTED_REPS = 12
CHOSEN_STEP = 2
TIMEZONE = "Africa/Tunis"
MORNING_UTC = datetime.datetime(2026, 11, 18, 10, 0, tzinfo=datetime.timezone.utc)
NO_CHECKS = {"pause_files": [], "check_microphone": False, "check_screen_share": False}
LONG_STREAK_DAYS = 12
NO_WRITES = 0
MEETING_LENGTH = datetime.timedelta(minutes=MEETING_PAUSE_MINUTES)
TOO_LONG_PAUSE_MINUTES = 100000
MODEL_SETTINGS = {"url": "https://models.example/v1", "model": "some-model", "key_file": ""}
REPS_WRITTEN = 11
REST_DAYS = 3


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
        self.can_ask_model = False
        self.ai_settings = DEFAULTS["ai"]

    def brain(self):
        return Brain(SqlStore(self.execute), OWNER_CHAT, clock=lambda: self.moment, chooser=seeded_random(),
                     can_ask_model=self.can_ask_model)

    def with_model(self):
        self.can_ask_model, self.ai_settings = True, MODEL_SETTINGS
        self.sync()

    def answer_model(self, outcome, response):
        return self.brain().model_answered(outcome["model"], response)

    def sync_report(self, cursor=None):
        pack = default_pack_raw()

        return {"config": config_with(conditions=NO_CHECKS, ai=self.ai_settings), "pack": pack, "pack_digest": pack_digest(pack),
                "timezone": TIMEZONE, "cursor": cursor}

    def sync(self, cursor=None):
        return self.brain().desktop(DESKTOP_SYNC, {"report": self.sync_report(cursor)})["response"]

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

    def play_max_test(self):
        self.send("/test")
        questions = len(self.brain().build_app().pack.test)
        self.send("/skip")

        for _ in range(questions - 1):
            self.send(str(TESTED_REPS))

        self.tap(f"test-step {CHOSEN_STEP}")

        return self.tap(f"test-step {CHOSEN_STEP}")

    def test_a_max_test_played_on_the_phone_is_recorded_like_the_desktop_one(self):
        self.sync()

        finished = self.play_max_test()

        tests = [event for event in self.brain().export()["events"] if event["type"] == EVENT_TEST]
        state = self.brain().store.load_state()
        pack = self.brain().build_app().pack
        self.assertEqual(len(tests), 1)
        self.assertNotIn(pack.test[0], tests[0]["results"])
        self.assertEqual(set(tests[0]["results"].values()), {TESTED_REPS})
        self.assertEqual(tests[0]["skill_steps"], {"handstand": CHOSEN_STEP - 1, "one_arm_pull_up": CHOSEN_STEP - 1})
        self.assertEqual(state["rungs"]["handstand"], CHOSEN_STEP - 1)
        self.assertIn("Targets set.", self.replies(finished))
        self.assertIn(TEST_NOT_RUNNING, self.replies(self.send("/skip")))

    def test_numbers_during_a_max_test_answer_the_test_and_not_a_waiting_rating(self):
        self.sync()
        self.command("now")
        token = self.pending()["token"]
        self.tap(f"answer {token} {ANSWER_DONE}")
        self.send("/test")

        self.send(str(TESTED_REPS))

        self.assertNotIn("typed", self.pending())

    def test_cancelling_a_max_test_saves_nothing(self):
        self.sync()
        self.send("/test")
        self.send(str(TESTED_REPS))

        self.send("/cancel")

        tests = [event for event in self.brain().export()["events"] if event["type"] == EVENT_TEST]
        self.assertEqual(tests, [])
        self.assertIn(TEST_NOT_RUNNING, self.replies(self.send("/skip")))

    def test_a_result_out_of_range_is_asked_again(self):
        self.sync()
        self.send("/test")

        self.send(str(MAXIMUM_TEST_RESULT + 1))
        self.send(str(TESTED_REPS))

        tests_state = self.brain().store.setting("max_test")
        self.assertEqual(tests_state["position"], 1)

    def test_a_max_test_in_progress_holds_challenges_back_until_it_goes_stale(self):
        self.sync()
        self.send("/test")

        self.assertEqual(self.brain().busy_reason(), STATUS_TESTING)

        self.moment += datetime.timedelta(seconds=TEST_SESSION_SECONDS)
        self.assertNotEqual(self.brain().busy_reason(), STATUS_TESTING)

    def test_the_retest_reminder_offers_to_start_the_test_on_the_phone(self):
        self.sync()

        outcome = self.brain().tick()

        buttons = [button["callback_data"] for row in
                   telegram_calls(outcome, METHOD_SEND)[0]["payload"]["reply_markup"]["inline_keyboard"] for button in row]
        self.assertIn(TEST_START, buttons)
        self.assertNotIn("test-window", buttons)

    def meeting_button(self, outcome):
        return next(button["callback_data"] for call in telegram_calls(outcome, METHOD_SEND)
                    for row in call["payload"]["reply_markup"]["inline_keyboard"] for button in row
                    if button["text"] == "Meeting")

    def test_the_meeting_button_holds_the_challenge_back_until_the_meeting_is_over(self):
        self.sync()
        state = self.brain().store.load_state()
        state["last_test_day"] = self.moment.date().isoformat()
        state["next_due"] = self.moment.timestamp()
        self.brain().store.save_state(state)
        button = self.meeting_button(self.command("now"))
        token = self.pending()["token"]

        self.tap(button)

        self.moment += MEETING_LENGTH - datetime.timedelta(minutes=1)
        self.assertEqual(self.brain().tick()["telegram"], [])

        self.moment += datetime.timedelta(minutes=1)
        reminder = self.brain().tick()
        self.assertEqual(reminder["text"], "remind")
        self.assertEqual(self.pending()["token"], token)

    def test_pause_in_telegram_holds_new_challenges_back_for_that_many_minutes(self):
        self.sync()

        self.assertIn("Paused until", self.replies(self.send("/pause 90")))

        self.moment += datetime.timedelta(minutes=89)
        self.assertEqual(self.brain().tick()["text"], "nothing due")

        self.moment += datetime.timedelta(minutes=1)
        self.assertNotEqual(self.brain().tick()["text"], "nothing due")

    def test_away_in_telegram_stores_the_day_and_lists_it(self):
        self.sync()

        self.assertIn("14:00", self.replies(self.send("/away tomorrow 14")))

        self.assertEqual(self.brain().store.load_state()["away_days"], {"2026-11-19": 14})
        self.assertIn("Out on", self.replies(self.send("/away")))

    def test_the_coach_says_how_to_set_it_up_when_there_is_no_model(self):
        self.sync()

        outcome = self.send("/coach")

        self.assertIsNone(outcome["model"])
        self.assertEqual(self.replies(outcome), AI_NOT_SET_UP)

    def test_the_coach_asks_the_model_and_sends_its_review(self):
        self.with_model()

        outcome = self.send("/coach")
        answered = self.answer_model(outcome, model_response("• Pull-ups stall: add a rep."))

        self.assertEqual(outcome["model"]["purpose"], PURPOSE_COACH)
        self.assertEqual(self.replies(answered), "• Pull-ups stall: add a rep.")

    def test_a_written_note_logs_the_set_once_and_clears_the_card_buttons(self):
        self.with_model()
        self.command("now")
        self.brain().remember_message(TAPPED_MESSAGE)

        outcome = self.send("did 11, could do 3 more")
        note = model_json({"answer": "done", "reps": REPS_WRITTEN, "feeling": "3+ left"})
        answered = self.answer_model(outcome, note)
        repeated = self.answer_model(outcome, note)

        sets = [event for event in self.brain().export()["events"] if event["type"] == EVENT_SET]
        self.assertEqual(outcome["model"]["purpose"], PURPOSE_NOTE)
        self.assertEqual([event["amount"] for event in sets], [REPS_WRITTEN])
        self.assertEqual(telegram_calls(answered, METHOD_CLEAR_BUTTONS)[0]["payload"]["message_id"], TAPPED_MESSAGE)
        self.assertIn("ignored", self.replies(repeated))

    def test_a_note_the_model_did_not_understand_changes_nothing(self):
        self.with_model()
        self.command("now")

        answered = self.answer_model(self.send("hmm"), None)

        self.assertEqual(self.replies(answered), NOTE_NOT_UNDERSTOOD)
        self.assertIsNotNone(self.pending())

    def test_text_with_a_waiting_card_but_no_model_gets_the_help(self):
        self.sync()
        self.command("now")

        self.assertIsNone(self.send("did 11")["model"])

    def test_text_without_a_waiting_card_gets_the_help(self):
        self.with_model()

        self.assertIsNone(self.send("hello")["model"])

    def test_pain_advice_offers_rest_buttons_that_rest_the_group(self):
        self.with_model()

        outcome = self.send("/pain my wrist hurts on push-ups")
        answered = self.answer_model(outcome, model_json({"advice": "Rest the wrist.", "rest": ["push"],
                                                          "days": REST_DAYS}))
        keyboard = telegram_calls(answered, METHOD_SEND)[0]["payload"]["reply_markup"]["inline_keyboard"]
        self.tap(keyboard[0][0]["callback_data"])

        self.assertEqual(keyboard[0][0]["callback_data"], f"rest push {REST_DAYS}")
        self.assertEqual(self.brain().store.load_state()["rested"], {"push": "2026-11-21"})

    def test_a_pause_longer_than_a_day_is_refused(self):
        self.sync()
        paused_before = self.brain().store.load_state()["paused_until"]

        self.assertIn("ignored", self.replies(self.send(f"/pause {TOO_LONG_PAUSE_MINUTES}")))
        self.assertEqual(self.brain().store.load_state()["paused_until"], paused_before)

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

    def test_a_sync_with_an_unchanged_config_writes_nothing(self):
        self.sync()
        self.moment += datetime.timedelta(minutes=1)
        writes = []
        recording = lambda statement, *parameters: (writes.append(statement) if statement.startswith(
            "INSERT INTO settings") else None) or self.execute(statement, *parameters)
        store = SqlStore(recording)
        Brain(store, clock=lambda: self.moment).desktop(DESKTOP_SYNC, {"report": self.sync_report()})

        self.assertEqual(len(writes), NO_WRITES)

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
