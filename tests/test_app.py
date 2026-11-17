import tempfile
import unittest
from pathlib import Path

from rep.app import ANSWER_DONE, ANSWER_LATER, ANSWER_SKIP, App
from rep.paths import Paths
from rep.progression import RATING_EASY, Challenge, KIND_HARD, target_of
from rep.store import EVENT_SESSION, EVENT_SET, EVENT_SKIP, FileStore, load_events
from tests.helpers import FIXED_NOW, config_with, default_pack, seeded_random

NO_CHECKS = {"pause_files": [], "check_microphone": False, "check_screen_share": False}
PUSH_CHALLENGE = Challenge(KIND_HARD, "push", "push_up", "clap_push_up")
REPS_DONE = 30


class RecordingNotifier:
    def __init__(self):
        self.cards = []

    def show(self, card):
        self.cards.append(card)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.paths = Paths(root / "config", root / "state")
        self.notifier = RecordingNotifier()
        self.app = self.fresh_app()

    def tearDown(self):
        self.directory.cleanup()

    def fresh_app(self):
        config = config_with(conditions=NO_CHECKS, display={"notifier": "terminal", "quickshell_kind": "workout",
                                                             "line_command": ""})

        return App(FileStore(self.paths), config, default_pack(), self.notifier, seeded_random(), clock=lambda: FIXED_NOW)

    def token(self):
        return self.app.state["pending"]["token"]

    def test_done_then_a_rating_logs_exactly_one_set_even_when_clicked_twice(self):
        self.app.start_challenge(PUSH_CHALLENGE)
        token = self.token()

        self.app.answer(token, ANSWER_DONE)
        self.app.answer(token, ANSWER_DONE)
        self.fresh_app().rate(token, RATING_EASY)
        result = self.fresh_app().rate(token, RATING_EASY)

        sets = [event for event in load_events(self.paths) if event["type"] == EVENT_SET]
        self.assertEqual(len(sets), 1)
        self.assertTrue(result.startswith("ignored"))

    def test_the_reps_actually_done_are_logged_and_the_next_target_grows_from_them(self):
        self.app.start_challenge(PUSH_CHALLENGE)
        token = self.token()

        self.app.answer(token, ANSWER_DONE)
        self.fresh_app().rate(token, RATING_EASY, REPS_DONE)

        sets = [event for event in load_events(self.paths) if event["type"] == EVENT_SET]
        self.assertEqual(sets[0]["amount"], REPS_DONE)
        step = self.app.pack.exercises["clap_push_up"].step
        self.assertEqual(self.fresh_app().state["targets"]["clap_push_up"], REPS_DONE + step)

    def test_the_rating_card_asks_for_the_reps_done_starting_from_the_target(self):
        self.app.start_challenge(PUSH_CHALLENGE)
        target = target_of(self.app.state, self.app.pack, "clap_push_up", self.app.scale)

        self.app.answer(self.token(), ANSWER_DONE)

        self.assertEqual(self.notifier.cards[-1].done_prompt, target)

    def test_an_answer_with_an_old_token_is_ignored(self):
        self.app.start_challenge(PUSH_CHALLENGE)

        result = self.app.answer("stale-token", ANSWER_SKIP)

        self.assertTrue(result.startswith("ignored"))
        self.assertIsNotNone(self.app.state["pending"])

    def test_later_keeps_the_challenge_and_moves_it_by_the_snooze_time(self):
        self.app.start_challenge(PUSH_CHALLENGE)

        self.app.answer(self.token(), ANSWER_LATER)

        snooze_seconds = self.app.config["schedule"]["snooze_minutes"] * 60
        self.assertEqual(self.app.state["next_due"], FIXED_NOW.timestamp() + snooze_seconds)
        self.assertEqual(self.app.state["pending"]["exercise"], "clap_push_up")

    def test_skip_logs_a_skip_and_clears_the_challenge(self):
        self.app.start_challenge(PUSH_CHALLENGE)

        self.app.answer(self.token(), ANSWER_SKIP)

        self.assertIsNone(self.app.state["pending"])
        self.assertEqual([event["type"] for event in load_events(self.paths)], [EVENT_SKIP])

    def test_a_session_is_logged_and_unknown_sessions_are_refused(self):
        self.assertEqual(self.app.log_session("upper"), "logged")
        self.assertTrue(self.app.log_session("arms").startswith("unknown"))

    def test_a_routine_replaces_the_built_in_sessions(self):
        config = config_with(conditions=NO_CHECKS, training={"routine": {"push": ["chest", "biceps"]}})
        app = App(FileStore(self.paths), config, default_pack(), self.notifier, seeded_random(), clock=lambda: FIXED_NOW)

        self.assertEqual(app.log_session("push"), "logged")
        self.assertTrue(app.log_session("upper").startswith("unknown"))
        self.assertEqual(app.today()["sessions"], {"push": "chest + biceps"})
        self.assertEqual(app.today()["trained"], ["push"])

        self.assertEqual([event["type"] for event in load_events(self.paths)], [EVENT_SESSION])

    def test_the_state_survives_a_restart_between_the_two_answer_steps(self):
        self.app.start_challenge(PUSH_CHALLENGE)
        token = self.token()
        self.app.answer(token, ANSWER_DONE)

        restarted = self.fresh_app()

        self.assertEqual(restarted.rate(token, RATING_EASY), "rated")


if __name__ == "__main__":
    unittest.main()
