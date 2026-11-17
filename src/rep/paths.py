import os
from dataclasses import dataclass
from pathlib import Path

APPLICATION_NAME = "rep"
CONFIG_FILE_NAME = "config.toml"
STATE_FILE_NAME = "state.json"
EVENTS_FILE_NAME = "events.jsonl"
TODAY_FILE_NAME = "today.json"
PACKS_DIRECTORY_NAME = "packs"


@dataclass(frozen=True)
class Paths:
    config_directory: Path
    state_directory: Path

    @property
    def config_file(self):
        return self.config_directory / CONFIG_FILE_NAME

    @property
    def packs_directory(self):
        return self.config_directory / PACKS_DIRECTORY_NAME

    @property
    def state_file(self):
        return self.state_directory / STATE_FILE_NAME

    @property
    def events_file(self):
        return self.state_directory / EVENTS_FILE_NAME

    @property
    def today_file(self):
        return self.state_directory / TODAY_FILE_NAME


def default_paths():
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))

    return Paths(config_home / APPLICATION_NAME, state_home / APPLICATION_NAME)
