import json
import subprocess

from rep.notifiers import rep_command

COMMAND_TIMEOUT_SECONDS = 5
INPUT_PLACEHOLDER = "{input}"
DONE_INPUT_LABEL = "reps done"


class QuickshellNotifier:
    def __init__(self, kind):
        self.kind = kind

    def show(self, card):
        typed = [INPUT_PLACEHOLDER] if card.done_prompt is not None else []
        extra = {
            "sticky": card.sticky,
            "actions": [{"label": button.label, "glyph": button.glyph,
                         "cmd": rep_command() + list(button.arguments) + typed} for button in card.buttons],
        }

        if card.done_prompt is not None:
            extra["input"] = {"label": DONE_INPUT_LABEL, "value": str(card.done_prompt)}
        command = ["qs", "ipc", "call", "osd", "rich", self.kind, card.title, card.body, json.dumps(extra)]

        try:
            subprocess.run(command, capture_output=True, timeout=COMMAND_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            pass
