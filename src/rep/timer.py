import shlex
import shutil
import subprocess
from pathlib import Path

from rep.notifiers import rep_command

UNIT_NAME = "rep"
TICK_INTERVAL_MINUTES = 3
BOOT_DELAY_MINUTES = 2
TIMER_ACCURACY_SECONDS = 30
SYSTEMD_USER_DIRECTORY = Path.home() / ".config" / "systemd" / "user"

SERVICE_TEMPLATE = """[Unit]
Description=rep: check whether a calisthenics challenge is due

[Service]
Type=oneshot
ExecStart={command} tick
"""

TIMER_TEMPLATE = """[Unit]
Description=rep: check every {interval} minutes whether a challenge is due

[Timer]
OnBootSec={boot}min
OnUnitActiveSec={interval}min
AccuracySec={accuracy}s

[Install]
WantedBy=timers.target
"""


def systemctl(*arguments):
    return subprocess.run(["systemctl", "--user", *arguments], capture_output=True, text=True)


def install_timer():
    if not shutil.which("systemctl"):
        return "systemd isn't available here: run `rep tick` every few minutes some other way (cron)."

    SYSTEMD_USER_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (SYSTEMD_USER_DIRECTORY / f"{UNIT_NAME}.service").write_text(SERVICE_TEMPLATE.format(command=shlex.join(rep_command())))
    (SYSTEMD_USER_DIRECTORY / f"{UNIT_NAME}.timer").write_text(TIMER_TEMPLATE.format(
        interval=TICK_INTERVAL_MINUTES, boot=BOOT_DELAY_MINUTES, accuracy=TIMER_ACCURACY_SECONDS))
    systemctl("daemon-reload")
    result = systemctl("enable", "--now", f"{UNIT_NAME}.timer")

    return "timer installed and started" if result.returncode == 0 else result.stderr.strip()


def uninstall_timer():
    systemctl("disable", "--now", f"{UNIT_NAME}.timer")

    for suffix in ("service", "timer"):
        (SYSTEMD_USER_DIRECTORY / f"{UNIT_NAME}.{suffix}").unlink(missing_ok=True)

    systemctl("daemon-reload")

    return "timer removed"
