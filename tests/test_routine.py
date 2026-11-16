import unittest

from rep.config import DEFAULTS
from rep.routine import RoutineError, parse_day, routine_allowances, session_allowances
from rep.wizard import ask_routine
from tests.helpers import config_with, default_pack

WEEKLY_CAPS = DEFAULTS["training"]["weekly_caps"]
SETS_PER_MUSCLE = DEFAULTS["training"]["sets_per_muscle"]


class RoutineTests(unittest.TestCase):
    def setUp(self):
        self.pack = default_pack()

    def test_a_day_is_read_with_plus_and_and_and_loose_spelling(self):
        self.assertEqual(parse_day("Push: chest + bicep and Shoulders", self.pack.muscles),
                         ("push", ["chest", "biceps", "shoulders"]))
        self.assertEqual(parse_day("pull: back, triceps, rear delts", self.pack.muscles),
                         ("pull", ["back", "triceps", "rear_delts"]))

    def test_unknown_muscles_and_missing_names_are_refused(self):
        with self.assertRaises(RoutineError):
            parse_day("push: chest, wings", self.pack.muscles)

        with self.assertRaises(RoutineError):
            parse_day("chest, biceps", self.pack.muscles)

    def test_each_day_counts_sets_for_the_groups_its_muscles_belong_to(self):
        routine = {"push": ["chest", "biceps", "shoulders"], "legs": ["legs", "core", "shoulders"]}

        allowances = routine_allowances(routine, self.pack.muscles, SETS_PER_MUSCLE, WEEKLY_CAPS)

        self.assertEqual(allowances["push"], {"push": 2 * SETS_PER_MUSCLE, "pull": SETS_PER_MUSCLE})
        self.assertEqual(allowances["legs"], {"legs": WEEKLY_CAPS["legs"], "core": WEEKLY_CAPS["core"],
                                              "push": SETS_PER_MUSCLE})

    def test_without_a_routine_the_built_in_sessions_stay(self):
        training = config_with()["training"]

        self.assertEqual(session_allowances(training, self.pack), DEFAULTS["training"]["session_allowances"])

    def test_the_wizard_reads_days_until_an_empty_line_and_retries_bad_ones(self):
        answers = iter(["push: chest, biceps", "pull: wings", "pull: back", ""])
        written = []

        routine = ask_routine(self.pack, {}, read=lambda prompt: next(answers), write=written.append)

        self.assertEqual(routine, {"push": ["chest", "biceps"], "pull": ["back"]})
        self.assertTrue(any("wings" in line for line in written))

    def test_the_wizard_keeps_the_current_routine_on_an_empty_first_line(self):
        current = {"push": ["chest"]}

        self.assertEqual(ask_routine(self.pack, current, read=lambda prompt: "", write=lambda line: None), current)


if __name__ == "__main__":
    unittest.main()
