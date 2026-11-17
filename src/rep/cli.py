import argparse
import tomllib
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rep.app import ANSWERS, App
from rep.backup import FORMAT_JSON, FORMATS, export_records, export_text, import_backup
from rep.catalog import DEFAULT_PACK_RESOURCE, PackError, load_pack
from rep.charts import stats_text
from rep.completion import COMPLETION_COMMAND, SHELLS, completion_script
from rep.config import DEFAULTS, ConfigMissing, load_config, merge, save_config
from rep.conditions import busy_reason
from rep.maxtest import ask_test, run_test
from rep.notifiers import Card, make_notifier, rep_command
from rep.notifiers.desktop import AWAIT_SUBCOMMAND, await_notification
from rep.paths import default_paths
from rep.progression import RATINGS
from rep.routine import RoutineError, describe_sessions
from rep.store import FileStore, MemoryStore, empty_state, load_events, load_state
from rep.cloud import DESKTOP_EXPORT, DESKTOP_IMPORT
from rep.launcher import cached_today
from rep.sync import SyncError, client_for, desktop_command, desktop_tick
from rep.timer import install_timer, uninstall_timer
from rep.wizard import run_wizard

TERMINALS = ("kitty", "foot", "alacritty", "wezterm", "gnome-terminal", "konsole", "xterm")
EXIT_PROBLEM = 1


SYNCED_COMMANDS = ("tick", "now", "answer", "rate", "session", "summary", "dismiss", "test", "today", "stats",
                   "routine", "export", "import", "sync-upload")


def pack_for(config):
    pack_file = config["training"]["pack_file"]

    return load_pack(os.path.expanduser(pack_file) if pack_file else None)


def pack_raw_for(config):
    pack_file = config["training"]["pack_file"]

    return json.loads(Path(os.path.expanduser(pack_file)).read_text() if pack_file else load_pack_text())


def synced_config(paths, command):
    if command not in SYNCED_COMMANDS or not paths.config_file.exists():
        return None

    config = load_config(paths)

    return config if config["sync"]["url"] else None


def forwarded_arguments(arguments):
    command = arguments.command

    if command == "answer":
        return [command, arguments.token, arguments.answer]

    if command == "rate":
        done = [] if arguments.done is None else [str(arguments.done)]

        return [command, arguments.token, str(arguments.rating)] + done

    if command == "session":
        return [command, arguments.kind]

    return [command]


def cloud_app(client, config):
    backup = client.call(DESKTOP_EXPORT)

    return App(MemoryStore(backup["state"], backup["events"]), config, pack_for(config),
               make_notifier(config["display"]), random.Random())


def sync_tick(client, paths, config):
    return desktop_tick(client, paths, config, pack_raw_for(config), make_notifier(config["display"]),
                        busy_reason(config["conditions"]), int(time.time()))


def sync_command(client, paths, config, forwarded):
    return desktop_command(client, paths, config, pack_raw_for(config), make_notifier(config["display"]),
                           busy_reason(config["conditions"]), int(time.time()), forwarded)


def local_app(config):
    return App(MemoryStore(empty_state(), []), config, pack_for(config), make_notifier(config["display"]),
               random.Random())


def dispatch_synced(paths, config, arguments):
    client = client_for(config)
    command = arguments.command

    if command == "tick":
        print(sync_tick(client, paths, config))
    elif command == "today":
        cached = cached_today(paths)

        if cached is None:
            sync_tick(client, paths, config)
            cached = cached_today(paths)

        print(cached)
    elif command == "routine":
        command_routine(local_app(config), arguments)
    elif command in ("stats", "export"):
        dispatch_read(cloud_app(client, config), arguments)
    elif command == "import":
        backup = json.loads(Path(arguments.file).read_text())
        records = {"events": backup.get("events", []), "state": backup.get("state") if arguments.with_state else None}
        print(f"Imported {client.call(DESKTOP_IMPORT, records)['added']} new events.")
    elif command == "sync-upload":
        records = {"events": load_events(paths), "state": load_state(paths)}
        print(f"Uploaded {client.call(DESKTOP_IMPORT, records)['added']} new events and your targets and ladders.")
    else:
        forwarded = forwarded_arguments(arguments)

        if command == "test":
            results, skill_steps = ask_test(cloud_app(client, config))
            forwarded = ["apply-test", json.dumps({"results": results, "skill_steps": skill_steps})]

        print(sync_command(client, paths, config, forwarded))


def dispatch_read(app, arguments):
    if arguments.command == "stats":
        print(stats_text(app, with_history=arguments.history))
    else:
        write_export(export_records(app.state, list(app.events), arguments.format), arguments)


def build_app(paths):
    config = load_config(paths)

    return App(FileStore(paths), config, pack_for(config), make_notifier(config["display"]), random.Random())


def command_init(paths, arguments):
    existing = None

    if paths.config_file.exists():
        with open(paths.config_file, "rb") as config_stream:
            existing = tomllib.load(config_stream)

    config = run_wizard(pack_for(merge(DEFAULTS, existing)) if existing else load_pack(), existing)
    save_config(paths, config)
    print(f"\nSaved to {paths.config_file}.")
    print("Next: `rep test` (sets your targets), then `rep install-timer`.")


def command_now(paths, arguments):
    print(build_app(paths).now())


def open_in_terminal(command):
    preferred = os.environ.get("TERMINAL")
    terminal = preferred if preferred and shutil.which(preferred) else next((name for name in TERMINALS if shutil.which(name)), None)

    if terminal is None:
        print(f"No terminal found: run `{shlex.join(command)}` yourself.")

        return

    script = f"{shlex.join(command)}; read -rp 'Enter to close' _"
    subprocess.Popen([terminal, "-e", "sh", "-c", script], start_new_session=True)


def command_export(paths, arguments):
    write_export(export_text(paths, arguments.format), arguments)


def write_export(text, arguments):
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


def command_routine(app, arguments):
    training = app.config["training"]
    descriptions = describe_sessions(training, training["session_allowances"])

    for session, description in descriptions.items():
        sets = ", ".join(f"{group} {count}" for group, count in training["session_allowances"][session].items())
        print(session if arguments.names else f"{session}: {description}  (counts as {sets})")


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
    rate.add_argument("done", type=int, nargs="?", help="reps (or seconds) you actually did")
    session = commands.add_parser("session", help="log a training session today")
    setattr(session.add_argument("kind"), COMPLETION_COMMAND, ("routine", "--names"))
    routine = commands.add_parser("routine", help="your training days and the muscles each one trains")
    routine.add_argument("--names", action="store_true", help="only the day names")
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
    completion = commands.add_parser("completion", help="print a shell completion script")
    completion.add_argument("shell", choices=SHELLS)
    commands.add_parser("dismiss")
    commands.add_parser("sync-upload", help="copy this computer's history and targets to the cloud (once)")
    waiting = commands.add_parser(AWAIT_SUBCOMMAND)
    waiting.add_argument("payload")

    return root


def dispatch(paths, arguments):
    command = arguments.command
    config = synced_config(paths, command)

    if config:
        dispatch_synced(paths, config, arguments)

        return
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
        print(build_app(paths).rate(arguments.token, arguments.rating, arguments.done))
    elif command == "routine":
        command_routine(build_app(paths), arguments)
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
    elif command == "completion":
        print(completion_script(parser(), arguments.shell), end="")
    elif command == AWAIT_SUBCOMMAND:
        await_notification(arguments.payload)
    elif command == "sync-upload":
        print("Sync isn't set up: add url and token under [sync] in your config first.", file=sys.stderr)
        sys.exit(EXIT_PROBLEM)


def main(argv=None):
    arguments = parser().parse_args(argv)

    try:
        dispatch(default_paths(), arguments)
    except ConfigMissing as missing:
        print(missing, file=sys.stderr)

        if arguments.command != "tick":
            sys.exit(EXIT_PROBLEM)
    except RoutineError as problem:
        print(f"Config problem: {problem}", file=sys.stderr)
        sys.exit(EXIT_PROBLEM)
    except PackError as problem:
        print(f"Exercise pack problem: {problem}", file=sys.stderr)
        sys.exit(EXIT_PROBLEM)
    except SyncError as problem:
        print(f"Sync problem: {problem}", file=sys.stderr)

        if arguments.command != "tick":
            sys.exit(EXIT_PROBLEM)
