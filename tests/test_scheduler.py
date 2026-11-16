import datetime
import unittest

from rep.progression import Challenge
from rep.scheduler import (ACTION_CHALLENGE, ACTION_NUDGE, ACTION_REMIND, ACTION_RETEST, ACTION_SCHEDULE_FIRST,
                           ACTION_SUMMARY, STAMP_RETEST, decide)
from rep.store import EVENT_TEST
from tests.helpers import FIXED_NOW, config_with, default_pack, event_at, fresh_state, seeded_random

NO_NUDGES = {"protein": "off", "bedtime": "off", "summary": "off"}
MINUTES_BEFORE_REMINDER = 5


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.pack = default_pack()
        self.config = config_with(nudges=NO_NUDGES)
        self.state = fresh_state()
        self.state["stamps"][STAMP_RETEST] = FIXED_NOW.date().isoformat()
        self.events = [event_at(EVENT_TEST, results={})]

    def decide(self, now=FIXED_NOW, busy=None):
        return decide(now, self.state, self.config, self.pack, self.events, busy, seeded_random())

    def test_the_first_tick_only_schedules_the_first_challenge(self):
        self.assertEqual(self.decide().action, ACTION_SCHEDULE_FIRST)

    def test_a_due_challenge_waits_while_the_user_is_busy(self):
        self.state["next_due"] = FIXED_NOW.timestamp() - 1

        self.assertIsNone(self.decide(busy="mic in use"))
        self.assertEqual(self.decide().action, ACTION_CHALLENGE)

    def test_an_unanswered_card_is_not_sent_again_before_the_reminder_interval(self):
        self.state["next_due"] = FIXED_NOW.timestamp() - 1
        shown = FIXED_NOW - datetime.timedelta(minutes=MINUTES_BEFORE_REMINDER)
        self.state["pending"] = {"token": "a", "shown_at": shown.timestamp()}

        self.assertIsNone(self.decide())
        later = FIXED_NOW + datetime.timedelta(minutes=self.config["schedule"]["reminder_minutes"])
        self.assertEqual(self.decide(now=later).action, ACTION_REMIND)

    def test_nothing_happens_outside_the_active_hours(self):
        self.state["next_due"] = 1
        night = FIXED_NOW.replace(hour=self.config["schedule"]["end_hour"])

        self.assertIsNone(self.decide(now=night))

    def test_nudges_and_the_summary_fire_once_a_day_at_their_time(self):
        self.config["nudges"] = {"protein": "20:00", "bedtime": "off", "summary": "21:00"}
        evening = FIXED_NOW.replace(hour=21, minute=30)

        self.assertEqual(self.decide(now=evening), type(self.decide(now=evening))(ACTION_NUDGE, "protein"))
        self.state["stamps"]["protein"] = evening.date().isoformat()
        self.assertEqual(self.decide(now=evening).action, ACTION_SUMMARY)

    def test_a_retest_is_suggested_when_there_was_never_a_test(self):
        self.events, self.state["stamps"] = [], {}

        self.assertEqual(self.decide().action, ACTION_RETEST)

    def test_a_new_challenge_is_a_challenge_object(self):
        self.state["next_due"] = 1

        self.assertIsInstance(self.decide().detail, Challenge)


if __name__ == "__main__":
    unittest.main()
