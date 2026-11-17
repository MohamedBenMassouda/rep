import unittest

from rep.catalog import skill_progress
from tests.helpers import default_pack

ONE_ARM_PULL_UP = "one_arm_pull_up"


class SkillProgressTests(unittest.TestCase):
    def setUp(self):
        self.pack = default_pack()
        self.ladder = self.pack.skills[ONE_ARM_PULL_UP]

    def test_a_practice_step_says_where_it_sits_and_what_unlocks_the_next_one(self):
        first_step = self.ladder.exercise_identifiers[0]

        progress = skill_progress(self.pack, self.ladder, first_step)

        self.assertEqual(progress, "Step 1 of 5 to the One-arm pull-up. "
                                   "6 per side unlocks Typewriter pull-up practice")

    def test_the_last_step_says_it_is_the_skill_itself(self):
        last_step = self.ladder.exercise_identifiers[-1]

        progress = skill_progress(self.pack, self.ladder, last_step)

        self.assertEqual(progress, "Step 5 of 5 to the One-arm pull-up, the skill itself")


if __name__ == "__main__":
    unittest.main()
