import unittest

from rep.app import App
from rep.assistant import (FEELING_NOT_SAID, NO_COACH_ANSWER, NOTE_DONE, NOTE_SKIP, coach_brief, coach_reply,
                           drafted_routine, note_answer, note_request, pack_request, pack_with_additions, pain_answer)
from rep.catalog import PackError
from rep.notifiers import OutboxNotifier
from rep.progression import KIND_BOSS, KIND_HARD, RATING_EASY, RATING_STEADY, Challenge
from rep.store import EVENT_SESSION, EVENT_SET, EVENT_SKIP, MemoryStore, empty_state
from rep.wizard import ask_drafted_routine
from tests.helpers import (FIXED_NOW, config_with, default_pack, default_pack_raw, event_at, model_json,
                           model_response, seeded_random)

PUSH_CHALLENGE = Challenge(KIND_HARD, "push", "push_up", "clap_push_up")
REPS_DONE = 11
TOO_MANY_REST_DAYS = 90
HOLLOW_ROCK = {"identifier": "hollow_body_rock", "name": "Hollow body rocks", "unit": "reps", "start": 3,
               "step": 1, "top": 8, "cue": "Lower back stays down."}
HOLLOW_LADDER = {"group": "core", "identifier": "hollow_body", "exercises": ["hollow_body_rock"]}


def app_with(events):
    return App(MemoryStore(empty_state(), events), config_with(), default_pack(), OutboxNotifier(), seeded_random(),
               clock=lambda: FIXED_NOW, busy_check=lambda: None)


def addition(exercises=(HOLLOW_ROCK,), ladders=(HOLLOW_LADDER,), skills=()):
    return {"exercises": list(exercises), "ladders": list(ladders), "skills": list(skills)}


class CoachTests(unittest.TestCase):
    def test_the_brief_names_the_week_sets_skips_and_training_days(self):
        events = [event_at(EVENT_SET, kind=KIND_HARD, group="push", ladder="push_up", exercise="clap_push_up",
                           amount=REPS_DONE, rating=RATING_STEADY),
                  event_at(EVENT_SKIP, kind=KIND_HARD, group="pull", ladder="pull_up", exercise="archer_pull_up",
                           amount="8 reps"),
                  event_at(EVENT_SESSION, session="upper")]

        brief = coach_brief(app_with(events))

        self.assertIn("Clap push-ups 11 reps (1–2 left)", brief)
        self.assertIn("skipped Archer pull-ups", brief)
        self.assertIn("training day upper", brief)
        self.assertIn("No max test yet", brief)

    def test_no_answer_from_the_model_gives_a_readable_reply(self):
        self.assertEqual(coach_reply(None), NO_COACH_ANSWER)
        self.assertEqual(coach_reply(model_response("• Good week")), "• Good week")


class NoteTests(unittest.TestCase):
    def test_the_question_offers_the_feelings_of_that_kind_of_card(self):
        app = app_with([])
        app.start_challenge(PUSH_CHALLENGE)

        request = note_request(app, "did 11, two left")

        self.assertIn("1–2 left", request["body"]["messages"][1]["content"])
        feelings = request["body"]["response_format"]["json_schema"]["schema"]["properties"]["feeling"]["enum"]
        self.assertIn(FEELING_NOT_SAID, feelings)

    def test_a_feeling_label_becomes_its_rating_and_unsaid_reps_become_nothing(self):
        done = note_answer(model_json({"answer": NOTE_DONE, "reps": REPS_DONE, "feeling": "3+ left"}), KIND_HARD)
        bare = note_answer(model_json({"answer": NOTE_SKIP, "reps": 0, "feeling": FEELING_NOT_SAID}), KIND_HARD)

        self.assertEqual(done, {"answer": NOTE_DONE, "reps": REPS_DONE, "rating": RATING_EASY})
        self.assertEqual(bare, {"answer": NOTE_SKIP, "reps": None, "rating": None})

    def test_boss_cards_have_their_own_feelings(self):
        note = note_answer(model_json({"answer": NOTE_DONE, "reps": REPS_DONE, "feeling": "Matched it"}), KIND_BOSS)

        self.assertEqual(note["rating"], RATING_STEADY)

    def test_an_answer_outside_the_choices_is_not_understood(self):
        self.assertIsNone(note_answer(model_json({"answer": "maybe", "reps": 1, "feeling": "x"}), KIND_HARD))
        self.assertIsNone(note_answer(None, KIND_HARD))


class PainTests(unittest.TestCase):
    def test_unknown_groups_are_dropped_and_the_days_kept_in_range(self):
        advice = pain_answer(model_json({"advice": " Rest it. ", "rest": ["push", "arms"], "days": TOO_MANY_REST_DAYS}),
                             default_pack())

        self.assertEqual(advice["advice"], "Rest it.")
        self.assertEqual(advice["rest"], ["push"])
        self.assertEqual(advice["days"], 28)

    def test_a_broken_answer_gives_no_advice(self):
        self.assertIsNone(pain_answer(model_json({"rest": []}), default_pack()))


class PackSuggestionTests(unittest.TestCase):
    def test_the_request_lists_the_existing_ladders_and_the_wish(self):
        request = pack_request({"url": "u", "model": "m"}, default_pack_raw(), "a dragon flag ladder")

        self.assertIn("push/push_up: clap_push_up", request["body"]["messages"][1]["content"])
        self.assertIn("Request: a dragon flag ladder", request["body"]["messages"][1]["content"])

    def test_a_new_ladder_with_new_exercises_is_added_and_validated(self):
        extended, added = pack_with_additions(default_pack_raw(), addition())

        self.assertEqual(extended["ladders"]["core"]["hollow_body"], ["hollow_body_rock"])
        self.assertIn("hollow_body_rock", added[0])
        self.assertNotIn("hollow_body_rock", default_pack_raw()["exercises"])

    def test_a_suggestion_that_reuses_an_existing_identifier_is_refused(self):
        reused = {**HOLLOW_LADDER, "exercises": ["clap_push_up"]}

        with self.assertRaises(PackError):
            pack_with_additions(default_pack_raw(), addition(exercises=({**HOLLOW_ROCK, "identifier": "clap_push_up"},),
                                                             ladders=(reused,)))

    def test_an_exercise_left_off_every_ladder_or_with_odd_numbers_is_refused(self):
        with self.assertRaises(PackError):
            pack_with_additions(default_pack_raw(), addition(ladders=()))

        with self.assertRaises(PackError):
            pack_with_additions(default_pack_raw(), addition(exercises=({**HOLLOW_ROCK, "top": 1},)))

        with self.assertRaises(PackError):
            pack_with_additions(default_pack_raw(), None)


class RoutineDraftTests(unittest.TestCase):
    def test_a_draft_becomes_routine_days_with_known_muscles(self):
        draft = model_json({"days": [{"name": "push", "muscles": ["chest", "triceps"]},
                                     {"name": "legs", "muscles": ["legs"]}]})

        self.assertEqual(drafted_routine(draft, default_pack()), {"push": ["chest", "triceps"], "legs": ["legs"]})

    def test_a_draft_with_a_bad_day_name_is_thrown_away(self):
        draft = model_json({"days": [{"name": "Push Day!", "muscles": ["chest"]}]})

        self.assertIsNone(drafted_routine(draft, default_pack()))

    def test_the_wizard_uses_a_draft_only_once_it_is_accepted(self):
        routine = {"push": ["chest"]}
        answers = iter(["push on mondays", "n"])

        refused = ask_drafted_routine(lambda description: routine, read=lambda prompt: next(answers),
                                      write=lambda line: None)
        accepted = ask_drafted_routine(lambda description: routine, read=lambda prompt: "push on mondays" if
                                       prompt.startswith("\n") else "", write=lambda line: None)

        self.assertIsNone(refused)
        self.assertEqual(accepted, routine)


if __name__ == "__main__":
    unittest.main()
