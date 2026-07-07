import hashlib
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

ACCEPTED_RE = re.compile(r"Accepted \S+ for (?P<user>\S+) from (?P<ip>[0-9a-fA-F:.]+)")
FAILED_RE = re.compile(r"Failed \S+ for (?:invalid user )?(?P<user>\S+) from (?P<ip>[0-9a-fA-F:.]+)")
AUTH_TS_RE = re.compile(r"^(?P<mon>\w{3})\s+(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})")


def parse_auth_line(line: str, year: int | None = None) -> dict[str, str] | None:
    match = ACCEPTED_RE.search(line)
    event_type = "ssh_login_success"
    if match is None:
        match = FAILED_RE.search(line)
        event_type = "ssh_login_failed"
    if match is None:
        return None

    occurred_at = parse_auth_timestamp(line, year)
    event_key = hashlib.sha256(f"{occurred_at}|{event_type}|{line}".encode()).hexdigest()
    return {
        "event_key": event_key,
        "event_type": event_type,
        "username": match.group("user"),
        "ip": match.group("ip"),
        "message": line.strip(),
        "occurred_at": occurred_at,
    }


def parse_auth_timestamp(line: str, year: int | None = None) -> str:
    year = year or datetime.now(UTC).year
    match = AUTH_TS_RE.match(line)
    if match is None:
        return datetime.now(UTC).isoformat()
    month = MONTHS.get(match.group("mon"), datetime.now(UTC).month)
    hour, minute, second = [int(part) for part in match.group("time").split(":")]
    dt = datetime(year, month, int(match.group("day")), hour, minute, second, tzinfo=UTC)
    return dt.isoformat()


def read_auth_events(paths: list[str], max_lines: int = 500) -> list[dict[str, str]]:
    lines = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.exists():
            lines.extend(path.read_text(errors="replace").splitlines()[-max_lines:])

    if not lines:
        lines = read_journalctl_lines(max_lines)

    events = []
    for line in lines[-max_lines:]:
        event = parse_auth_line(line)
        if event is not None:
            events.append(event)
    return events


def read_journalctl_lines(max_lines: int) -> list[str]:
    try:
        completed = subprocess.run(
            ["journalctl", "-u", "ssh", "-u", "sshd", "-n", str(max_lines), "--no-pager"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except OSError:
        return []
    return completed.stdout.splitlines()
