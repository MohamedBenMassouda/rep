import os
import random
import stat
import tempfile
import unittest
from pathlib import Path

from rep.lines import line_for
from tests.helpers import default_pack

QUIP = "Thwip!"


class LineTests(unittest.TestCase):
    def test_a_line_command_in_the_home_folder_is_found_through_a_tilde(self):
        with tempfile.TemporaryDirectory() as home:
            script = Path(home) / "quip.sh"
            script.write_text(f"#!/bin/sh\necho {QUIP} $1\n")
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
            previous_home = os.environ.get("HOME")
            os.environ["HOME"] = home

            try:
                line = line_for("done", default_pack(), {"line_command": "~/quip.sh {kind}"}, random.Random())
            finally:
                os.environ["HOME"] = previous_home

        self.assertEqual(line, f"{QUIP} done")

    def test_without_a_line_command_the_pack_supplies_the_line(self):
        line = line_for("done", default_pack(), {"line_command": ""}, random.Random())

        self.assertIn(line, default_pack().lines["done"])


if __name__ == "__main__":
    unittest.main()
