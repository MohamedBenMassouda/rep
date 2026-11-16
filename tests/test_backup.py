import tempfile
import unittest
from pathlib import Path

from rep.backup import FORMAT_JSON, export_text, import_backup
from rep.paths import Paths
from rep.store import EVENT_SET, append_event, load_events
from tests.helpers import event_at


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.source = Paths(root / "a" / "config", root / "a" / "state")
        self.target = Paths(root / "b" / "config", root / "b" / "state")

    def tearDown(self):
        self.directory.cleanup()

    def test_importing_the_same_backup_twice_adds_each_event_once(self):
        append_event(self.source, event_at(EVENT_SET, amount=10))
        append_event(self.source, event_at(EVENT_SET, amount=12))
        backup = export_text(self.source, FORMAT_JSON)

        first = import_backup(self.target, backup, include_state=True)
        second = import_backup(self.target, backup, include_state=True)

        self.assertEqual((first, second), (2, 0))
        self.assertEqual(len(load_events(self.target)), 2)


if __name__ == "__main__":
    unittest.main()
