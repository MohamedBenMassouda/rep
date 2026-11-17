import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rep.config import save_config
from rep.launcher import main
from rep.paths import default_paths
from tests.helpers import config_with

CACHED_TODAY = '{"done": 3}'
CLOUD_URL = "https://rep.example"


class LauncherTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        environment = {"XDG_CONFIG_HOME": str(root / "config"), "XDG_STATE_HOME": str(root / "state")}
        patcher = mock.patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.paths = default_paths()
        self.paths.state_directory.mkdir(parents=True)
        self.paths.today_file.write_text(CACHED_TODAY)

    def run_today(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output), mock.patch("rep.cli.main") as full_cli:
            main(["today"])

        return output.getvalue().strip(), full_cli

    def test_with_sync_on_today_prints_the_cached_numbers_without_the_full_cli(self):
        save_config(self.paths, config_with(sync={"url": CLOUD_URL, "token": "secret"}))

        printed, full_cli = self.run_today()

        self.assertEqual(printed, CACHED_TODAY)
        full_cli.assert_not_called()

    def test_without_sync_today_is_computed_by_the_full_cli(self):
        save_config(self.paths, config_with())

        printed, full_cli = self.run_today()

        self.assertEqual(printed, "")
        full_cli.assert_called_once()


if __name__ == "__main__":
    unittest.main()
