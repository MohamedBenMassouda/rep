import json
import subprocess

from rep.notifiers import rep_command

APPLICATION_NAME = "rep"
STICKY_URGENCY = "critical"
NORMAL_URGENCY = "normal"
COMMAND_TIMEOUT_SECONDS = 5
AWAIT_SUBCOMMAND = "await-notification"


class DesktopNotifier:
    def show(self, card):
        if not card.buttons:
            self.send(card, wait=False)

            return

        payload = json.dumps({"title": card.title, "body": card.body, "sticky": card.sticky,
                              "buttons": [[button.label, list(button.arguments)] for button in card.buttons]})
        subprocess.Popen(rep_command() + [AWAIT_SUBCOMMAND, payload], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def send(self, card, wait):
        command = ["notify-send", "--app-name", APPLICATION_NAME,
                   "--urgency", STICKY_URGENCY if card.sticky else NORMAL_URGENCY]

        for index, button in enumerate(card.buttons):
            command += ["--action", f"{index}={button.label}"]

        if wait:
            command.append("--wait")

        command += [card.title, card.body]

        try:
            if wait:
                return subprocess.run(command, capture_output=True, text=True).stdout.strip()

            subprocess.run(command, capture_output=True, timeout=COMMAND_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            return ""

        return ""


def await_notification(payload_text):
    from rep.notifiers import Button, Card

    payload = json.loads(payload_text)
    buttons = tuple(Button(label, 0, tuple(arguments)) for label, arguments in payload["buttons"])
    card = Card(payload["title"], payload["body"], payload["sticky"], buttons)
    chosen = DesktopNotifier().send(card, wait=True)

    if chosen.isdigit() and int(chosen) < len(buttons):
        subprocess.run(rep_command() + list(buttons[int(chosen)].arguments))
