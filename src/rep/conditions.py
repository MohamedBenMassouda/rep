import json
import os
import shutil
import subprocess

COMMAND_TIMEOUT_SECONDS = 5
MONITOR_SOURCE_SUFFIX = ".monitor"
SCREEN_SHARE_NODE_PREFIX = '"node.name": "xdph'
REASON_PAUSED = "paused"
REASON_MICROPHONE = "microphone in use"
REASON_SCREEN_SHARE = "screen shared"


def run_quietly(*command):
    if not shutil.which(command[0]):
        return ""

    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def expand(path_template):
    return os.path.expandvars(os.path.expanduser(path_template))


def microphone_in_use():
    sources_text = run_quietly("pactl", "-f", "json", "list", "sources")
    outputs_text = run_quietly("pactl", "-f", "json", "list", "source-outputs")

    try:
        sources = {source["index"]: source["name"] for source in json.loads(sources_text or "[]")}
        recordings = json.loads(outputs_text or "[]")
    except ValueError:
        return False

    return any(not sources.get(recording.get("source"), "").endswith(MONITOR_SOURCE_SUFFIX) for recording in recordings)


def screen_shared():
    return SCREEN_SHARE_NODE_PREFIX in run_quietly("pw-dump")


def busy_reason(conditions):
    if any(os.path.exists(expand(pause_file)) for pause_file in conditions["pause_files"]):
        return REASON_PAUSED

    if conditions["check_microphone"] and microphone_in_use():
        return REASON_MICROPHONE

    if conditions["check_screen_share"] and screen_shared():
        return REASON_SCREEN_SHARE

    return None
