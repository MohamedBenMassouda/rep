import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from rep.cloud import DESKTOP_COMMAND, DESKTOP_SYNC
from rep.notifiers import card_from_dict

SYNC_FILE_NAME = "sync.json"
SYNC_SECTION = "sync"
REQUEST_TIMEOUT_SECONDS = 10
DESKTOP_ROUTE = "/desktop/"
CARD_FRESH_SECONDS = 600
LOCALTIME_LINK = Path("/etc/localtime")
ZONEINFO_MARKER = "zoneinfo/"
DEFAULT_TIMEZONE = "UTC"
AUTHORIZATION_SCHEME = "Bearer "
JSON_CONTENT_TYPE = "application/json"


class SyncError(RuntimeError):
    pass


def urllib_post(url, body, token):
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": AUTHORIZATION_SCHEME + token,
                                              "Content-Type": JSON_CONTENT_TYPE})

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError) as problem:
        raise SyncError(f"the cloud didn't answer ({problem})") from problem


class SyncClient:
    def __init__(self, url, token, post=urllib_post):
        self.url, self.token, self.post = url.rstrip("/"), token, post

    def call(self, action, body=None):
        return self.post(self.url + DESKTOP_ROUTE + action, body or {}, self.token)


def client_for(config, post=urllib_post):
    settings = config["sync"]

    return SyncClient(settings["url"], settings["token"], post) if settings["url"] else None


def local_timezone():
    if os.environ.get("TZ"):
        return os.environ["TZ"].lstrip(":")

    target = os.path.realpath(LOCALTIME_LINK)

    return target.split(ZONEINFO_MARKER, 1)[1] if ZONEINFO_MARKER in target else DEFAULT_TIMEZONE


def sync_file(paths):
    return paths.state_directory / SYNC_FILE_NAME


def read_sync_state(paths):
    try:
        return json.loads(sync_file(paths).read_text())
    except (OSError, ValueError):
        return {"cursor": None, "open": None}


def write_sync_state(paths, sync_state):
    paths.state_directory.mkdir(parents=True, exist_ok=True)
    temporary_file = sync_file(paths).with_suffix(".tmp")
    temporary_file.write_text(json.dumps(sync_state))
    temporary_file.replace(sync_file(paths))


def desktop_report(paths, config, pack_raw, busy):
    shared_config = {section: values for section, values in config.items() if section != SYNC_SECTION}

    return {"config": shared_config, "pack": pack_raw, "timezone": local_timezone(), "busy": busy,
            "cursor": read_sync_state(paths)["cursor"]}


def apply_catch_up(paths, notifier, response, now_seconds):
    sync_state = read_sync_state(paths)
    pending = response["pending"]

    if sync_state["open"] and sync_state["open"] != pending:
        notifier.dismiss()

    fresh_cards = [card_from_dict(entry["card"]) for entry in response["cards"]
                   if now_seconds - entry["time"] < CARD_FRESH_SECONDS]

    for card in fresh_cards:
        notifier.show(card)

    showing_pending = any(card.sticky for card in fresh_cards) or sync_state["open"] == pending
    write_sync_state(paths, {"cursor": response["cursor"], "open": pending if showing_pending else None})
    paths.today_file.write_text(json.dumps(response["today"]))

    return len(fresh_cards)


def desktop_tick(client, paths, config, pack_raw, notifier, busy, now_seconds):
    response = client.call(DESKTOP_SYNC, desktop_report(paths, config, pack_raw, busy))
    shown = apply_catch_up(paths, notifier, response, now_seconds)

    return busy or f"synced, {shown} new cards"


def desktop_command(client, paths, config, pack_raw, notifier, busy, now_seconds, arguments):
    report = desktop_report(paths, config, pack_raw, busy)
    response = client.call(DESKTOP_COMMAND, {"arguments": arguments, "report": report})
    apply_catch_up(paths, notifier, response, now_seconds)

    return response["text"]
