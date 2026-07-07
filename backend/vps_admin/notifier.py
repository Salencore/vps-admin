from datetime import UTC, datetime, timedelta

from .config import get_settings
from .db import connect, get_setting


class Notifier:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def send(self, key: str, text: str, reply_markup: dict | None = None) -> bool:
        if not self._should_send(key):
            return False
        token = get_setting("telegram_bot_token", self.settings.telegram_bot_token)
        chat_id = get_setting("telegram_chat_id", self.settings.telegram_chat_id)
        if not token or not chat_id:
            return False

        import httpx

        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        self._mark_sent(key)
        return True

    def _should_send(self, key: str) -> bool:
        threshold = datetime.now(UTC) - timedelta(seconds=self.settings.alert_dedup_seconds)
        with connect() as conn:
            row = conn.execute("SELECT last_sent_at FROM notification_state WHERE key = ?", (key,)).fetchone()
        if row is None:
            return True
        return datetime.fromisoformat(row["last_sent_at"]) < threshold

    def _mark_sent(self, key: str) -> None:
        now = datetime.now(UTC).isoformat()
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO notification_state (key, last_sent_at)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET last_sent_at = excluded.last_sent_at
                """,
                (key, now),
            )
