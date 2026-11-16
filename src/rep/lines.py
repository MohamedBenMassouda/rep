import os
import shlex
import subprocess

COMMAND_TIMEOUT_SECONDS = 5
KIND_PLACEHOLDER = "{kind}"


def line_for(kind, pack, display, chooser):
    command_template = display.get("line_command", "")

    if command_template:
        command = [os.path.expanduser(part) for part in shlex.split(command_template.replace(KIND_PLACEHOLDER, kind))]

        try:
            custom = subprocess.run(command, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            custom = ""

        if custom:
            return custom

    return pack.random_line(kind, chooser)
