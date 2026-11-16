import argparse
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from rep.app import ANSWERS, SESSION_KINDS, App
from rep.backup import FORMAT_JSON, FORMATS, export_text, import_backup
from rep.catalog import DEFAULT_PACK_RESOURCE, PackError, load_pack
from rep.charts import stats_text
from rep.config import ConfigMissing, load_config, save_config
from rep.maxtest import run_test
from rep.notifiers import Card, make_notifier, rep_command
from rep.notifiers.desktop import AWAIT_SUBCOMMAND, await_notification
from rep.paths import default_paths
from rep.progression import RATINGS, choose_challenge
from rep.timer import install_timer, uninstall_timer
from rep.wizard import run_wizard

TERMINALS = ("kitty", "foot", "alacritty", "wezterm", "gnome-terminal", "konsole", "xterm")
EXIT_PROBLEM = 1


def pack_for(config):
    pack_file = config["training"]["pack_file"]

    return load_pack(os.path.expanduser(pack_file) if pack_file else None)


def build_app(paths):
    config = load_config(paths)

    return App(paths, config, pack_for(config), make_notifier(config["display"]), random.Random())


def command_init(paths, arguments):
    existing = None

    try:
        existing = load_config(paths)
    except ConfigMissing:
        pass

    config = run_wizard(pack_for(existing) if existing else load_pack(), existing)
    save_config(paths, config)
    print(f"\nSaved to {paths.config_file}.")
    print("Next: `rep test` (sets your targets), then `rep install-timer`.")


def command_now(paths, arguments):
    app = build_app(paths)

    if app.state.get("pending"):
        app.show_pending()

        return

    challenge = choose_challenge(app.state, app.pack, app.config["training"], app.config["profile"]["skills"],
                                 app.events, app.clock(), app.chooser)

    if challenge is None:
        print("Nothing to offer: every weekly cap is full and no skills are chosen.")

        return

    app.start_challenge(challenge)


def open_in_terminal(command):
    preferred = os.environ.get("TERMINAL")
    terminal = preferred if preferred and shutil.which(preferred) else next((name for name in TERMINALS if shutil.which(name)), None)

    if terminal is None:
        print(f"No terminal found: run `{shlex.join(command)}` yourself.")

        return

    script = f"{shlex.join(command)}; read -rp 'Enter to close' _"
    subprocess.Popen([terminal, "-e", "sh", "-c", script], start_new_session=True)


def command_export(paths, arguments):
    text = export_text(paths, arguments.format)

    if arguments.output:
        Path(arguments.output).write_text(text)
        print(f"Exported to {arguments.output}.")
    else:
        print(text)


def command_import(paths, arguments):
    added = import_backup(paths, Path(arguments.file).read_text(), arguments.with_state)
    print(f"Imported {added} new events.")


def command_pack(paths, arguments):
    destination = paths.packs_directory / DEFAULT_PACK_RESOURCE

    if arguments.action == "export":
        paths.packs_directory.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(json.loads(load_pack_text()), indent=2, ensure_ascii=False))
        print(f"Copied the default pack to {destination}.")
        print(f'Edit it, then set pack_file = "{destination}" under [training] in {paths.config_file}.')
    else:
        config = load_config(paths)
        print(config["training"]["pack_file"] or "built-in default pack")


def load_pack_text():
    from importlib import resources

    return resources.files("rep.data").joinpath(DEFAULT_PACK_RESOURCE).read_text()


def parser():
    root = argparse.ArgumentParser(prog="rep", description="Calisthenics challenges through the day.")
    commands = root.add_subparsers(dest="command", required=True, metavar="command")
    commands.add_parser("init", help="set up your profile and schedule")
    commands.add_parser("tick", help="show whatever is due (the timer runs this)")
    commands.add_parser("now", help="a challenge right now")
    answer = commands.add_parser("answer", help="answer a challenge card")
    answer.add_argument("token")
    answer.add_argument("answer", choices=ANSWERS)
    rate = commands.add_parser("rate", help="say how many reps were left")
    rate.add_argument("token")
    rate.add_argument("rating", type=int, choices=RATINGS)
    session = commands.add_parser("session", help="log a training session today")
    session.add_argument("kind", choices=SESSION_KINDS)
    commands.add_parser("test", help="max test: sets ladders and targets")
    commands.add_parser("test-window", help="run the max test in a terminal window")
    stats = commands.add_parser("stats", help="targets, ladders, caps and progress")
    stats.add_argument("--history", action="store_true", help="add progress charts and test comparison")
    commands.add_parser("today", help="today's numbers as JSON (for widgets)")
    commands.add_parser("summary", help="show today's summary")
    export = commands.add_parser("export", help="export your history")
    export.add_argument("--format", choices=FORMATS, default=FORMAT_JSON)
    export.add_argument("--output")
    imported = commands.add_parser("import", help="import a JSON export")
    imported.add_argument("file")
    imported.add_argument("--with-state", action="store_true", help="also replace targets and ladders")
    pack = commands.add_parser("pack", help="show or copy the exercise pack")
    pack.add_argument("action", choices=("path", "export"))
    commands.add_parser("install-timer", help="run `rep tick` every few minutes (systemd)")
    commands.add_parser("uninstall-timer", help="remove the timer")
    commands.add_parser("dismiss")
    waiting = commands.add_parser(AWAIT_SUBCOMMAND)
    waiting.add_argument("payload")

    return root


def dispatch(paths, arguments):
    command = arguments.command
    simple = {
        "init": command_init,
        "now": command_now,
        "export": command_export,
        "import": command_import,
        "pack": command_pack,
    }

    if command in simple:
        simple[command](paths, arguments)
    elif command == "tick":
        print(build_app(paths).tick())
    elif command == "answer":
        print(build_app(paths).answer(arguments.token, arguments.answer))
    elif command == "rate":
        print(build_app(paths).rate(arguments.token, arguments.rating))
    elif command == "session":
        print(build_app(paths).log_session(arguments.kind))
    elif command == "test":
        run_test(build_app(paths))
    elif command == "test-window":
        open_in_terminal(rep_command() + ["test"])
    elif command == "stats":
        print(stats_text(build_app(paths), with_history=arguments.history))
    elif command == "today":
        print(json.dumps(build_app(paths).today()))
    elif command == "summary":
        app = build_app(paths)
        app.notifier.show(Card(*app.summary_lines()))
    elif command == "install-timer":
        print(install_timer())
    elif command == "uninstall-timer":
        print(uninstall_timer())
    elif command == AWAIT_SUBCOMMAND:
        await_notification(arguments.payload)


def main(argv=None):
    arguments = parser().parse_args(argv)

    try:
        dispatch(default_paths(), arguments)
    except ConfigMissing as missing:
        print(missing, file=sys.stderr)
        sys.exit(EXIT_PROBLEM)
    except PackError as problem:
        print(f"Exercise pack problem: {problem}", file=sys.stderr)
        sys.exit(EXIT_PROBLEM)
