import json
import subprocess

from rep.notifiers import rep_command

COMMAND_TIMEOUT_SECONDS = 5


class QuickshellNotifier:
    def __init__(self, kind):
        self.kind = kind

    def show(self, card):
        extra = {
            "sticky": card.sticky,
            "actions": [{"label": button.label, "glyph": button.glyph, "cmd": rep_command() + list(button.arguments)}
                        for button in card.buttons],
        }
        command = ["qs", "ipc", "call", "osd", "rich", self.kind, card.title, card.body, json.dumps(extra)]

        try:
            subprocess.run(command, capture_output=True, timeout=COMMAND_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            pass
