import datetime
import unittest

from rep.away import away_day, away_plan_lines, end_hour_on, weekly_away, weekly_away_text
from rep.config import DEFAULTS
from tests.helpers import FIXED_NOW

TODAY = FIXED_NOW.date()
FRIDAY = datetime.date(2026, 11, 20)
TUESDAY = datetime.date(2026, 11, 24)
OUT_HOUR = 14
EARLIER_HOUR = 9
LATE_HOUR = 23
PAST_DAY = "2026-11-01"


def schedule_with(away):
    return {**DEFAULTS["schedule"], "away": away}


class AwayTests(unittest.TestCase):
    def test_a_weekday_name_means_its_next_occurrence_and_today_counts(self):
        self.assertEqual(away_day("friday", TODAY), FRIDAY)
        self.assertEqual(away_day("Fri", TODAY), FRIDAY)
        self.assertEqual(away_day("wednesday", TODAY), TODAY)
        self.assertEqual(away_day("tomorrow", TODAY), TODAY + datetime.timedelta(days=1))

    def test_a_past_date_or_an_unknown_word_is_no_away_day(self):
        self.assertIsNone(away_day(PAST_DAY, TODAY))
        self.assertIsNone(away_day("someday", TODAY))
        self.assertIsNone(away_day("fr", TODAY))

    def test_weekly_away_days_are_read_from_short_weekday_names_and_written_back(self):
        weekly = weekly_away("tue 14, Thursday 15")

        self.assertEqual(weekly, {"tuesday": 14, "thursday": 15})
        self.assertEqual(weekly_away(weekly_away_text(weekly)), weekly)
        self.assertEqual(weekly_away("none"), {})
        self.assertIsNone(weekly_away("tue"))
        self.assertIsNone(weekly_away("tue 25"))

    def test_a_weekly_away_day_ends_the_challenges_at_its_hour(self):
        schedule = schedule_with({"tuesday": OUT_HOUR})

        self.assertEqual(end_hour_on(TUESDAY, schedule, {}), OUT_HOUR)
        self.assertEqual(end_hour_on(FRIDAY, schedule, {}), schedule["end_hour"])

    def test_a_one_off_day_wins_over_the_weekly_one_and_home_brings_the_full_day_back(self):
        schedule = schedule_with({"tuesday": OUT_HOUR})

        self.assertEqual(end_hour_on(TUESDAY, schedule, {TUESDAY.isoformat(): EARLIER_HOUR}), EARLIER_HOUR)
        self.assertEqual(end_hour_on(TUESDAY, schedule, {TUESDAY.isoformat(): None}), schedule["end_hour"])

    def test_an_away_hour_never_stretches_the_day_past_the_usual_end(self):
        schedule = schedule_with({"tuesday": LATE_HOUR})

        self.assertEqual(end_hour_on(TUESDAY, schedule, {}), schedule["end_hour"])

    def test_the_plan_lists_weekly_days_and_only_the_upcoming_one_off_days(self):
        lines = away_plan_lines(schedule_with({"tuesday": OUT_HOUR}),
                                {PAST_DAY: OUT_HOUR, FRIDAY.isoformat(): EARLIER_HOUR}, TODAY)

        self.assertEqual(len(lines), 2)
        self.assertIn("14:00", lines[0])
        self.assertIn("9:00", lines[1])


if __name__ == "__main__":
    unittest.main()
