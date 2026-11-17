import sys

from rep.config import ConfigMissing, load_config
from rep.paths import default_paths

CACHED_TODAY_ARGUMENTS = ["today"]


def cached_synced_today(paths):
    try:
        config = load_config(paths)
    except ConfigMissing:
        return None

    if not config["sync"]["url"]:
        return None

    return cached_today(paths)


def cached_today(paths):
    try:
        return paths.today_file.read_text()
    except OSError:
        return None


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv

    if arguments == CACHED_TODAY_ARGUMENTS:
        cached = cached_synced_today(default_paths())

        if cached is not None:
            print(cached)

            return

    from rep.cli import main as full_main

    full_main(argv)
