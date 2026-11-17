import datetime
import unittest

from rep.progression import (KIND_BOSS, KIND_HARD, KIND_SKILL, RATING_EASY, RATING_FAILURE, RATING_STEADY,
                             apply_rating, cap_usage, choose_challenge, current_exercise, streak_days, target_of)
from rep.store import EVENT_SESSION, EVENT_SET
from tests.helpers import ADVANCED_SCALE, FIXED_NOW, config_with, default_pack, event_at, fresh_state, seeded_random

PULL_UP_START = 10
LADDER_TOP_MINUS_ONE = 14
REPS_DONE_ABOVE_TARGET = 13
REPS_DONE_BELOW_TARGET = 6
RATING_SEQUENCE = (RATING_STEADY, RATING_STEADY, RATING_FAILURE, RATING_STEADY, RATING_STEADY, RATING_STEADY,
                   RATING_EASY, RATING_EASY, RATING_EASY, RATING_EASY)
CHOICES_TO_SAMPLE = 60


class RatingTests(unittest.TestCase):
    def setUp(self):
        self.pack = default_pack()
        self.state = fresh_state()

    def rate(self, rating, exercise="chest_to_bar_pull_up", done=None):
        return apply_rating(self.state, self.pack, exercise, rating, ADVANCED_SCALE, done)

    def test_an_easy_set_raises_the_target_by_one_step(self):
        self.rate(RATING_EASY)

        self.assertEqual(target_of(self.state, self.pack, "chest_to_bar_pull_up", ADVANCED_SCALE), PULL_UP_START + 1)

    def test_an_easy_set_with_more_reps_done_than_asked_raises_the_target_from_those_reps(self):
        self.rate(RATING_EASY, done=REPS_DONE_ABOVE_TARGET)

        self.assertEqual(target_of(self.state, self.pack, "chest_to_bar_pull_up", ADVANCED_SCALE),
                         REPS_DONE_ABOVE_TARGET + 1)

    def test_a_steady_set_with_more_reps_done_than_asked_makes_those_reps_the_target(self):
        self.rate(RATING_STEADY, done=REPS_DONE_ABOVE_TARGET)

        self.assertEqual(target_of(self.state, self.pack, "chest_to_bar_pull_up", ADVANCED_SCALE), REPS_DONE_ABOVE_TARGET)

    def test_a_failed_set_with_fewer_reps_done_lowers_the_target_to_those_reps(self):
        self.rate(RATING_FAILURE, done=REPS_DONE_BELOW_TARGET)

        self.assertEqual(target_of(self.state, self.pack, "chest_to_bar_pull_up", ADVANCED_SCALE), REPS_DONE_BELOW_TARGET)

    def test_typing_exactly_the_target_counts_the_same_as_typing_nothing(self):
        typed_state, untyped_state = fresh_state(), fresh_state()

        for rating in RATING_SEQUENCE:
            typed = target_of(typed_state, self.pack, "chest_to_bar_pull_up", ADVANCED_SCALE)
            typed_unlock = apply_rating(typed_state, self.pack, "chest_to_bar_pull_up", rating, ADVANCED_SCALE, typed)
            untyped_unlock = apply_rating(untyped_state, self.pack, "chest_to_bar_pull_up", rating, ADVANCED_SCALE)

            self.assertEqual(typed_unlock, untyped_unlock)
            self.assertEqual(typed_state, untyped_state)

    def test_three_steady_sets_in_a_row_raise_the_target(self):
        for _ in range(2):
            self.rate(RATING_STEADY)

        self.assertEqual(target_of(self.state, self.pack, "chest_to_bar_pull_up", ADVANCED_SCALE), PULL_UP_START)
        self.rate(RATING_STEADY)
        self.assertEqual(target_of(self.state, self.pack, "chest_to_bar_pull_up", ADVANCED_SCALE), PULL_UP_START + 1)

    def test_a_failed_set_keeps_the_target_and_resets_the_steady_run(self):
        self.rate(RATING_STEADY)
        self.rate(RATING_FAILURE)

        self.assertEqual(self.state["steady_answers"]["chest_to_bar_pull_up"], 0)
        self.assertEqual(target_of(self.state, self.pack, "chest_to_bar_pull_up", ADVANCED_SCALE), PULL_UP_START)

    def test_reaching_the_top_of_a_rung_moves_the_ladder_to_the_next_movement(self):
        self.state["targets"]["chest_to_bar_pull_up"] = LADDER_TOP_MINUS_ONE

        unlocked = self.rate(RATING_EASY)

        self.assertEqual(unlocked, "explosive_pull_up")
        self.assertEqual(current_exercise(self.state, self.pack.ladders["pull_up"]), "explosive_pull_up")


class CapTests(unittest.TestCase):
    def test_a_logged_upper_session_uses_its_allowance_of_the_weekly_cap(self):
        pack, config = default_pack(), config_with()
        events = [event_at(EVENT_SESSION, session="upper")]

        usage = cap_usage(events, pack.groups, config["training"]["session_allowances"], FIXED_NOW.date())

        self.assertEqual((usage["push"], usage["pull"], usage["legs"]), (6, 6, 0))

    def test_sets_from_last_week_do_not_count_against_this_week(self):
        pack, config = default_pack(), config_with()
        last_week = FIXED_NOW - datetime.timedelta(days=7)
        events = [event_at(EVENT_SET, now=last_week, kind=KIND_HARD, group="push")]

        usage = cap_usage(events, pack.groups, config["training"]["session_allowances"], FIXED_NOW.date())

        self.assertEqual(usage["push"], 0)


class ChoiceTests(unittest.TestCase):
    def setUp(self):
        self.pack, self.config, self.chooser = default_pack(), config_with(), seeded_random()

    def choose(self, events, now=FIXED_NOW, state=None):
        return choose_challenge(state or fresh_state(), self.pack, self.config["training"],
                                self.config["profile"]["skills"], events, now, self.chooser)

    def test_trained_groups_are_never_chosen_on_the_same_day(self):
        events = [event_at(EVENT_SESSION, session="upper")]

        groups = {self.choose(events).group for _ in range(CHOICES_TO_SAMPLE)}

        self.assertFalse(groups & {"push", "pull"})

    def test_when_every_cap_is_full_only_skill_practice_is_offered(self):
        events = [event_at(EVENT_SESSION, session="full")] * 3

        kinds = {self.choose(events).kind for _ in range(CHOICES_TO_SAMPLE)}

        self.assertEqual(kinds, {KIND_SKILL})

    def test_without_skills_and_with_full_caps_nothing_is_offered(self):
        self.config["profile"]["skills"] = []
        events = [event_at(EVENT_SESSION, session="full")] * 3

        self.assertIsNone(self.choose(events))

    def test_a_boss_appears_at_most_once_a_week(self):
        afternoon = FIXED_NOW.replace(hour=16)
        boss = event_at(EVENT_SET, now=afternoon, kind=KIND_BOSS, group="pull")

        kinds = {self.choose([boss], now=afternoon).kind for _ in range(CHOICES_TO_SAMPLE)}

        self.assertNotIn(KIND_BOSS, kinds)


class StreakTests(unittest.TestCase):
    def test_a_streak_counts_consecutive_days_that_reached_the_minimum(self):
        minimum = config_with()["training"]["streak_minimum"]
        days = [FIXED_NOW - datetime.timedelta(days=offset) for offset in (1, 2)]
        events = [event_at(EVENT_SET, now=day) for day in days for _ in range(minimum)]

        self.assertEqual(streak_days(events, FIXED_NOW.date(), minimum), 2)


if __name__ == "__main__":
    unittest.main()
