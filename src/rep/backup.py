import csv
import io
import json

from rep.store import load_events, load_state, save_state, write_events

FORMAT_JSON = "json"
FORMAT_CSV = "csv"
FORMATS = (FORMAT_JSON, FORMAT_CSV)
CSV_COLUMNS = ("id", "day", "time", "type", "kind", "group", "ladder", "exercise", "amount", "rating", "session")


def export_text(paths, export_format):
    events = load_events(paths)

    if export_format == FORMAT_CSV:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(events)

        return buffer.getvalue()

    return json.dumps({"state": load_state(paths), "events": events}, indent=1)


def import_backup(paths, backup_text, include_state):
    backup = json.loads(backup_text)
    events_by_id = {event["id"]: event for event in load_events(paths) if "id" in event}
    before = len(events_by_id)

    for event in backup.get("events", []):

        if "id" in event:
            events_by_id[event["id"]] = event

    merged = sorted(events_by_id.values(), key=lambda event: event.get("time", 0))
    write_events(paths, merged)

    if include_state and "state" in backup:
        save_state(paths, backup["state"])

    return len(merged) - before
