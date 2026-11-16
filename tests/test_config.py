import tempfile
import unittest
from pathlib import Path

from rep.config import ConfigMissing, load_config
from rep.paths import Paths

SETTINGS_WITHOUT_PROFILE = '[display]\nline_command = "my-quips {kind}"\n'


class ConfigTests(unittest.TestCase):
    def test_settings_saved_before_init_do_not_count_as_a_set_up_profile(self):
        with tempfile.TemporaryDirectory() as root:
            paths = Paths(Path(root) / "config", Path(root) / "state")
            paths.config_directory.mkdir(parents=True)
            paths.config_file.write_text(SETTINGS_WITHOUT_PROFILE)

            with self.assertRaises(ConfigMissing):
                load_config(paths)


if __name__ == "__main__":
    unittest.main()
