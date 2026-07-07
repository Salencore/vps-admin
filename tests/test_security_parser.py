from vps_admin.collectors.security import parse_auth_line


def test_parse_successful_ssh_login():
    event = parse_auth_line("Jul  6 12:34:56 host sshd[100]: Accepted publickey for root from 203.0.113.10 port 52222 ssh2", 2026)

    assert event is not None
    assert event["event_type"] == "ssh_login_success"
    assert event["username"] == "root"
    assert event["ip"] == "203.0.113.10"
    assert event["occurred_at"] == "2026-07-06T12:34:56+00:00"


def test_parse_failed_invalid_user_login():
    event = parse_auth_line("Jul  6 12:35:01 host sshd[101]: Failed password for invalid user admin from 198.51.100.7 port 41222 ssh2", 2026)

    assert event is not None
    assert event["event_type"] == "ssh_login_failed"
    assert event["username"] == "admin"
    assert event["ip"] == "198.51.100.7"


def test_ignores_unrelated_lines():
    assert parse_auth_line("Jul  6 12:35:01 host sudo: pam_unix(sudo:session): session opened") is None
