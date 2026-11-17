import datetime
import unittest
import zoneinfo

from rep.app import ANSWER_DONE
from rep.cloud import BUSY_REPORT_FRESH_SECONDS, NOT_CONFIGURED, Brain, SqlStore
from rep.progression import RATING_STEADY
from rep.store import EVENT_SET, EVENT_TEST, new_event
from tests.helpers import config_with, default_pack_raw, seeded_random, sqlite_execute

TIMEZONE = "Africa/Tunis"
MORNING_UTC = datetime.datetime(2026, 11, 18, 10, 0, tzinfo=datetime.timezone.utc)
NO_CHECKS = {"pause_files": [], "check_microphone": False, "check_screen_share": False}
LONG_STREAK_DAYS = 12
ONLY_THE_BUSY_REPORT = 1


def unreadable_history():
    raise AssertionError("the history was read")


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.execute = sqlite_execute(self)
        self.moment = MORNING_UTC

    def brain(self):
        return Brain(SqlStore(self.execute), clock=lambda: self.moment, chooser=seeded_random())

    def sync_report(self, busy=None, cursor=None):
        return {"config": config_with(conditions=NO_CHECKS), "pack": default_pack_raw(), "timezone": TIMEZONE,
                "busy": busy, "cursor": cursor}

    def sync(self, busy=None, cursor=None):
        return self.brain().desktop_sync(self.sync_report(busy, cursor))

    def pending(self):
        return self.brain().store.load_state()["pending"]

    def command(self, *arguments):
        return self.brain().command(list(arguments))

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
        Brain(store, clock=lambda: self.moment).desktop_sync(self.sync_report())

        self.assertEqual(len(writes), ONLY_THE_BUSY_REPORT)

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
