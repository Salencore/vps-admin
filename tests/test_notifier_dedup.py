from datetime import UTC, datetime, timedelta

from vps_admin.db import connect, init_db
from vps_admin.notifier import Notifier


def test_notifier_dedup_uses_last_sent(monkeypatch, tmp_path):
    monkeypatch.setenv("VPS_ADMIN_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("VPS_ADMIN_ALERT_DEDUP_SECONDS", "900")
    init_db()
    notifier = Notifier()

    assert notifier._should_send("container:test")
    notifier._mark_sent("container:test")
    assert not notifier._should_send("container:test")

    old = (datetime.now(UTC) - timedelta(seconds=901)).isoformat()
    with connect() as conn:
        conn.execute("UPDATE notification_state SET last_sent_at = ? WHERE key = ?", (old, "container:test"))

    assert notifier._should_send("container:test")
