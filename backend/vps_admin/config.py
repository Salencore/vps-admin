import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    db_path: str = "./data/vps_admin.sqlite3"
    jwt_secret: str = "change-this-long-random-secret"
    token_ttl_minutes: int = 720
    poll_interval_seconds: int = 30
    auth_log_paths: str = "/var/log/auth.log,/var/log/secure"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_admin_ids: str = ""
    cpu_alert_percent: int = 90
    ram_alert_percent: int = 90
    disk_alert_percent: int = 90
    alert_dedup_seconds: int = 900
    cors_origins: str = ""
    frontend_dir: str = "./frontend"

    @property
    def auth_log_path_list(self) -> list[str]:
        return [item.strip() for item in self.auth_log_paths.split(",") if item.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def telegram_admin_id_set(self) -> set[int]:
        ids = set()
        for item in self.telegram_admin_ids.split(","):
            item = item.strip()
            if item:
                ids.add(int(item))
        return ids


@lru_cache
def get_settings() -> Settings:
    return Settings(
        db_path=os.getenv("VPS_ADMIN_DB_PATH", Settings.db_path),
        jwt_secret=os.getenv("VPS_ADMIN_JWT_SECRET", Settings.jwt_secret),
        token_ttl_minutes=int(os.getenv("VPS_ADMIN_TOKEN_TTL_MINUTES", Settings.token_ttl_minutes)),
        poll_interval_seconds=int(os.getenv("VPS_ADMIN_POLL_INTERVAL_SECONDS", Settings.poll_interval_seconds)),
        auth_log_paths=os.getenv("VPS_ADMIN_AUTH_LOG_PATHS", Settings.auth_log_paths),
        telegram_bot_token=os.getenv("VPS_ADMIN_TELEGRAM_BOT_TOKEN", Settings.telegram_bot_token),
        telegram_chat_id=os.getenv("VPS_ADMIN_TELEGRAM_CHAT_ID", Settings.telegram_chat_id),
        telegram_admin_ids=os.getenv("VPS_ADMIN_TELEGRAM_ADMIN_IDS", Settings.telegram_admin_ids),
        cpu_alert_percent=int(os.getenv("VPS_ADMIN_CPU_ALERT_PERCENT", Settings.cpu_alert_percent)),
        ram_alert_percent=int(os.getenv("VPS_ADMIN_RAM_ALERT_PERCENT", Settings.ram_alert_percent)),
        disk_alert_percent=int(os.getenv("VPS_ADMIN_DISK_ALERT_PERCENT", Settings.disk_alert_percent)),
        alert_dedup_seconds=int(os.getenv("VPS_ADMIN_ALERT_DEDUP_SECONDS", Settings.alert_dedup_seconds)),
        cors_origins=os.getenv("VPS_ADMIN_CORS_ORIGINS", Settings.cors_origins),
        frontend_dir=os.getenv("VPS_ADMIN_FRONTEND_DIR", Settings.frontend_dir),
    )
