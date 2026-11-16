import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from rep.cli import parser
from rep.completion import SHELL_BASH, SHELLS, completion_script

HIDDEN_COMMANDS = ("dismiss", "await-notification")


class CompletionTest(unittest.TestCase):
    def test_every_script_lists_the_visible_commands_and_hides_the_internal_ones(self):
        for shell in SHELLS:
            script = completion_script(parser(), shell)

            self.assertIn("install-timer", script)
            self.assertIn("done skip later", script)

            for hidden in HIDDEN_COMMANDS:
                self.assertNotIn(hidden, script)

    def test_every_script_parses_in_its_own_shell(self):
        for shell in SHELLS:
            if shutil.which(shell) is None:
                continue

            with tempfile.TemporaryDirectory() as directory:
                script_file = Path(directory) / "rep-completion"
                script_file.write_text(completion_script(parser(), shell))
                result = subprocess.run([shell, "-n", str(script_file)], capture_output=True, text=True)

            self.assertEqual(result.returncode, 0, f"{shell}: {result.stderr}")

    def test_bash_offers_the_answers_after_a_token(self):
        if shutil.which(SHELL_BASH) is None:
            self.skipTest("bash is not installed")

        script = completion_script(parser(), SHELL_BASH)
        probe = 'COMP_WORDS=(rep answer abc ""); COMP_CWORD=3; _rep; echo "${COMPREPLY[@]}"'
        result = subprocess.run([SHELL_BASH, "-c", script + probe], capture_output=True, text=True)

        self.assertEqual(result.stdout.split(), ["done", "skip", "later"])
