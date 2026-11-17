import shutil
import subprocess
import sys
from dataclasses import dataclass, field

DETECTION_TIMEOUT_SECONDS = 3
QUICKSHELL_TARGET_MARKER = "target osd"


@dataclass(frozen=True)
class Button:
    label: str
    glyph: int
    arguments: tuple


@dataclass(frozen=True)
class Card:
    title: str
    body: str
    sticky: bool = False
    buttons: tuple = field(default_factory=tuple)
    done_prompt: int | None = None


def card_to_dict(card):
    return {
        "title": card.title,
        "body": card.body,
        "sticky": card.sticky,
        "buttons": [{"label": button.label, "glyph": button.glyph, "arguments": list(button.arguments)}
                    for button in card.buttons],
        "done_prompt": card.done_prompt,
    }


def card_from_dict(fields):
    buttons = tuple(Button(button["label"], button["glyph"], tuple(button["arguments"])) for button in fields["buttons"])

    return Card(fields["title"], fields["body"], fields["sticky"], buttons, fields.get("done_prompt"))


class OutboxNotifier:
    def __init__(self):
        self.cards = []

    def show(self, card):
        self.cards.append(card)

    def dismiss(self):
        pass


def rep_command():
    installed = shutil.which("rep")

    return [installed] if installed else [sys.executable, "-m", "rep"]


def quickshell_available():
    if not shutil.which("qs"):
        return False

    try:
        listing = subprocess.run(["qs", "ipc", "show"], capture_output=True, text=True, timeout=DETECTION_TIMEOUT_SECONDS).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False

    return QUICKSHELL_TARGET_MARKER in listing


def desktop_available():
    return bool(shutil.which("notify-send"))


def make_notifier(display):
    from rep.notifiers.desktop import DesktopNotifier
    from rep.notifiers.quickshell import QuickshellNotifier
    from rep.notifiers.terminal import TerminalNotifier

    chosen = display["notifier"]

    if chosen == "quickshell" or (chosen == "auto" and quickshell_available()):
        return QuickshellNotifier(display["quickshell_kind"])

    if chosen == "desktop" or (chosen == "auto" and desktop_available()):
        return DesktopNotifier()

    return TerminalNotifier()
