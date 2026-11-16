import unittest

from rep.maxtest import apply_results
from tests.helpers import default_pack, fresh_state

ONE_ARM_PUSH_UP_MAX = 8
ARCHER_PULL_UP_MAX = 7
TOO_FEW_REPS = 2


class MaxTestTests(unittest.TestCase):
    def setUp(self):
        self.pack, self.state = default_pack(), fresh_state()

    def test_the_ladder_starts_at_the_hardest_movement_done_for_real_at_seventy_percent(self):
        apply_results(self.state, self.pack, {"clap_push_up": 25, "one_arm_push_up": ONE_ARM_PUSH_UP_MAX}, {})

        push_up_ladder = self.pack.ladders["push_up"]
        self.assertEqual(push_up_ladder.exercise_identifiers[self.state["rungs"]["push_up"]], "one_arm_push_up")
        self.assertEqual(self.state["targets"]["one_arm_push_up"], round(ONE_ARM_PUSH_UP_MAX * 0.7))

    def test_a_result_below_the_minimum_does_not_count_as_the_real_level(self):
        apply_results(self.state, self.pack, {"chest_to_bar_pull_up": 12, "archer_pull_up": TOO_FEW_REPS}, {})

        self.assertEqual(self.state["rungs"]["pull_up"], 0)

    def test_a_chosen_skill_step_wins_over_tested_results(self):
        apply_results(self.state, self.pack, {"archer_pull_up": ARCHER_PULL_UP_MAX}, {"one_arm_pull_up": 2})

        self.assertEqual(self.state["rungs"]["one_arm_pull_up"], 2)


if __name__ == "__main__":
    unittest.main()
