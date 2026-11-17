import shlex

from rep.notifiers import rep_command


class TerminalNotifier:
    def show(self, card):
        print(card.title)
        print(f"  {card.body}")

        for button in card.buttons:
            print(f"  {button.label}: {shlex.join(rep_command() + list(button.arguments))}")

    def dismiss(self):
        pass
