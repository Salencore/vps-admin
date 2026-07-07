# VPS Admin Telegram

Telegram-админка для VPS: мониторинг сервера, Docker-контейнеров, SSH-событий, логи и безопасные действия через inline-кнопки.

Главный режим работы - Telegram bot polling. Веб API/dashboard оставлен в коде как запасной слой, но Docker Compose по умолчанию запускает именно Telegram-бота и не открывает порт `8080`.

## Что умеет MVP

- `/status` - CPU, RAM, disk, uptime, hostname, OS, network counters.
- `/containers` - список Docker-контейнеров, статус, health, CPU/RAM stats.
- Inline-кнопки контейнера: `Логи`, `Start`, `Stop`, `Restart`.
- `/security` - последние SSH login/fail события из `/var/log/auth.log`, `/var/log/secure` или `journalctl`.
- `/audit` - журнал административных действий.
- Фоновые Telegram-уведомления:
  - контейнер остановлен или unhealthy;
  - высокий CPU/RAM/disk;
  - новый SSH login/fail.
- Антиспам уведомлений через dedup interval.
- Доступ только для Telegram ID из `VPS_ADMIN_TELEGRAM_ADMIN_IDS`.

В сервисе нет web-shell. Управление ограничено заранее разрешенными действиями.

## Быстрый запуск на VPS

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin
sudo systemctl enable --now docker

sudo git clone -b codex/vps-admin https://github.com/Salencore/vps-admin.git /opt/vps-admin
cd /opt/vps-admin

sudo cp .env.example .env
sudo nano .env
```

Заполни `.env`:

```env
VPS_ADMIN_TELEGRAM_BOT_TOKEN=123456:telegram_bot_token
VPS_ADMIN_TELEGRAM_CHAT_ID=123456789
VPS_ADMIN_TELEGRAM_ADMIN_IDS=123456789
VPS_ADMIN_DB_PATH=/app/data/vps_admin.sqlite3
VPS_ADMIN_AUTH_LOG_PATHS=/host/var/log/auth.log,/host/var/log/secure
```

Где взять Telegram ID:

1. Напиши своему боту `/id`.
2. Если бот уже запущен без admin id, он ответит твоим ID.
3. Добавь этот ID в `VPS_ADMIN_TELEGRAM_ADMIN_IDS`.

Запуск:

```bash
sudo docker compose up -d --build
sudo docker compose logs -f
```

После запуска напиши боту:

```text
/start
```

## Обновление на сервере

```bash
cd /opt/vps-admin
sudo git pull
sudo docker compose down
sudo docker compose up -d --build
sudo docker compose logs -f
```

## Команды бота

- `/id` - показать твой Telegram ID.
- `/start` - главное меню.
- `/status` - состояние сервера.
- `/containers` - контейнеры и кнопки управления.
- `/security` - SSH-события.
- `/audit` - журнал действий.

## Docker Compose

Compose монтирует:

- `/var/run/docker.sock` для управления Docker;
- `/var/log` read-only для чтения auth logs;
- volume `vps_admin_data` для SQLite.

Docker socket опасен: если кто-то получит доступ к боту или токену, он сможет управлять контейнерами на VPS. Храни токен бота в секрете и обязательно ограничивай доступ через `VPS_ADMIN_TELEGRAM_ADMIN_IDS`.

## Systemd без Docker

```bash
sudo useradd --system --home /opt/vps-admin --shell /usr/sbin/nologin vpsadmin
sudo mkdir -p /opt/vps-admin
sudo git clone -b codex/vps-admin https://github.com/Salencore/vps-admin.git /opt/vps-admin
cd /opt/vps-admin

sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo cp .env.example .env
sudo nano .env

sudo cp systemd/vps-admin.service /etc/systemd/system/vps-admin.service
sudo systemctl daemon-reload
sudo systemctl enable --now vps-admin
sudo journalctl -u vps-admin -f
```

Для systemd-режима пользователю `vpsadmin` нужен доступ к Docker socket, если нужны команды управления контейнерами.

## Проверки

```bash
PYTHONPATH=backend pytest tests
```

## Безопасность

- Не добавляй произвольный shell в Telegram.
- Не пересылай `.env` и токен бота.
- Используй отдельного Telegram-бота только для этой админки.
- Добавляй в `VPS_ADMIN_TELEGRAM_ADMIN_IDS` только свои ID.
- При утечке токена сразу перевыпусти его через BotFather.
