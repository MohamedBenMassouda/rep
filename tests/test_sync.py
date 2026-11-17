import datetime
import json
import tempfile
import unittest
from pathlib import Path

from rep.cloud import Brain, SqlStore
from rep.paths import Paths
from rep.launcher import cached_today
from rep.sync import (CARD_FRESH_SECONDS, SyncClient, desktop_command, desktop_tick, read_sync_state,
                      write_sync_state)
from tests.helpers import config_with, default_pack_raw, seeded_random, sqlite_execute

TOKEN = "desktop-secret"
CLOUD_URL = "https://rep.example"
MORNING_UTC = datetime.datetime(2026, 11, 18, 10, 0, tzinfo=datetime.timezone.utc)
FAR_AHEAD_CURSOR = 999
NO_CHECKS = {"pause_files": [], "check_microphone": False, "check_screen_share": False}


class RecordingNotifier:
    def __init__(self):
        self.cards, self.dismissals = [], 0

    def show(self, card):
        self.cards.append(card)

    def dismiss(self):
        self.dismissals += 1


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.paths = Paths(root / "config", root / "state")
        self.execute = sqlite_execute(self)
        self.moment = MORNING_UTC
        self.notifier = RecordingNotifier()
        self.client = SyncClient(CLOUD_URL, TOKEN, self.post)
        self.calls = 0

    def tearDown(self):
        self.directory.cleanup()

    def brain(self):
        return Brain(SqlStore(self.execute), clock=lambda: self.moment, chooser=seeded_random())

    def post(self, url, body, token):
        self.calls += 1
        self.assertEqual(token, TOKEN)
        action = url.rsplit("/", 1)[1]

        return json.loads(json.dumps(self.brain().desktop(action, json.loads(json.dumps(body)))))

    def config(self):
        return config_with(conditions=NO_CHECKS, sync={"url": CLOUD_URL, "token": TOKEN})

    def tick(self):
        return desktop_tick(self.client, self.paths, self.config(), default_pack_raw(), self.notifier, None,
                            int(self.moment.timestamp()))

    def desktop(self, *arguments):
        return desktop_command(self.client, self.paths, self.config(), default_pack_raw(), self.notifier, None,
                               int(self.moment.timestamp()), list(arguments))

    def phone_command(self, *arguments):
        return self.brain().command(list(arguments))

    def test_a_card_from_the_cloud_shows_on_the_desktop_once(self):
        self.tick()
        self.phone_command("now")

        self.tick()
        self.tick()

        self.assertEqual(len(self.notifier.cards), 1)

    def test_the_first_desktop_tick_does_not_replay_older_cards(self):
        self.tick()
        self.phone_command("now")
        self.paths.state_directory.joinpath("sync.json").unlink()

        self.tick()

        self.assertEqual(self.notifier.cards, [])

    def test_a_card_answered_on_the_phone_leaves_the_desktop(self):
        self.tick()
        self.phone_command("now")
        self.tick()
        token = self.brain().store.load_state()["pending"]["token"]

        self.phone_command("answer", token, "skip")
        self.tick()

        self.assertEqual(self.notifier.dismissals, 1)

    def test_cards_from_while_the_desktop_was_off_are_not_shown_late(self):
        self.tick()
        self.phone_command("now")
        self.moment += datetime.timedelta(seconds=CARD_FRESH_SECONDS)

        self.tick()

        self.assertEqual(self.notifier.cards, [])

    def test_a_command_from_the_desktop_takes_one_round_trip_and_shows_its_card(self):
        self.tick()
        self.calls = 0

        self.desktop("now")

        self.assertEqual(self.calls, 1)
        self.assertEqual(len(self.notifier.cards), 1)

    def test_every_sync_leaves_todays_numbers_for_widgets_without_asking_the_cloud(self):
        self.tick()
        self.desktop("session", "upper")

        self.assertEqual(json.loads(cached_today(self.paths))["trained"], ["upper"])

    def test_a_desktop_ahead_of_a_recreated_cloud_still_gets_new_cards(self):
        self.tick()
        write_sync_state(self.paths, {"cursor": FAR_AHEAD_CURSOR, "open": None})
        self.tick()

        self.phone_command("now")
        self.tick()

        self.assertEqual(len(self.notifier.cards), 1)
        self.assertLess(read_sync_state(self.paths)["cursor"], FAR_AHEAD_CURSOR)

    def test_the_sync_token_stays_on_the_desktop(self):
        self.tick()

        self.assertNotIn("sync", self.brain().store.setting("config"))


if __name__ == "__main__":
    unittest.main()
