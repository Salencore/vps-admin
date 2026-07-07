import asyncio
import html
import logging
import os
from functools import wraps
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .collectors.docker import DockerCollector
from .collectors.system import get_overview
from .config import get_settings
from .db import add_audit, init_db, list_audit, list_security_events
from .monitor import Monitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
docker_collector = DockerCollector()


def is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    allowed = settings.telegram_admin_id_set
    return user_id in allowed if allowed else False


def admin_only(handler):
    @wraps(handler)
    async def wrapper(event: Message | CallbackQuery, *args: Any, **kwargs: Any):
        user = event.from_user
        if not is_admin(user.id if user else None):
            text = "Нет доступа. Узнай свой Telegram ID командой /id и добавь его в VPS_ADMIN_TELEGRAM_ADMIN_IDS."
            if isinstance(event, CallbackQuery):
                await event.answer("Нет доступа", show_alert=True)
                return
            await event.answer(text)
            return
        return await handler(event, *args)

    return wrapper


def main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Статус сервера", callback_data="status")
    builder.button(text="Контейнеры", callback_data="containers")
    builder.button(text="Security", callback_data="security")
    builder.button(text="Audit", callback_data="audit")
    builder.adjust(2)
    return builder.as_markup()


def container_keyboard(container_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Логи", callback_data=f"logs:{container_id}"),
                InlineKeyboardButton(text="Restart", callback_data=f"act:restart:{container_id}"),
            ],
            [
                InlineKeyboardButton(text="Start", callback_data=f"act:start:{container_id}"),
                InlineKeyboardButton(text="Stop", callback_data=f"act:stop:{container_id}"),
            ],
        ]
    )


def fmt_bytes(value: int | float) -> str:
    size = float(value or 0)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if size < 10 and unit != "B" else f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.0f} TB"


def fmt_uptime(seconds: int) -> str:
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    return f"{days}d {hours}h {minutes}m"


def status_text() -> str:
    overview = get_overview()
    return (
        "<b>VPS status</b>\n"
        f"Host: <code>{html.escape(overview['hostname'])}</code>\n"
        f"OS: <code>{html.escape(overview['platform'])}</code>\n"
        f"Uptime: <b>{fmt_uptime(overview['uptime_seconds'])}</b>\n\n"
        f"CPU: <b>{overview['cpu_percent']}%</b>\n"
        f"RAM: <b>{overview['memory']['percent']}%</b> "
        f"({fmt_bytes(overview['memory']['used'])}/{fmt_bytes(overview['memory']['total'])})\n"
        f"Disk: <b>{overview['disk']['percent']}%</b> "
        f"({fmt_bytes(overview['disk']['used'])}/{fmt_bytes(overview['disk']['total'])})\n"
        f"Network: sent {fmt_bytes(overview['network']['bytes_sent'])}, recv {fmt_bytes(overview['network']['bytes_recv'])}"
    )


async def send_containers(target: Message | CallbackQuery) -> None:
    containers = docker_collector.list_containers()
    if not containers:
        text = "Контейнеры не найдены или Docker недоступен."
        if isinstance(target, CallbackQuery):
            await target.message.answer(text)
        else:
            await target.answer(text)
        return

    for item in containers:
        stats = item.get("stats") or {}
        text = (
            f"<b>{html.escape(str(item.get('name') or item.get('id')))}</b>\n"
            f"ID: <code>{html.escape(str(item.get('id')))}</code>\n"
            f"Image: <code>{html.escape(str(item.get('image') or '-'))}</code>\n"
            f"Status: <b>{html.escape(str(item.get('status') or '-'))}</b>"
        )
        if item.get("health"):
            text += f" / {html.escape(str(item['health']))}"
        text += f"\nCPU: {stats.get('cpu_percent', 0)}% · RAM: {stats.get('memory_percent', 0)}%"

        if isinstance(target, CallbackQuery):
            await target.message.answer(text, reply_markup=container_keyboard(str(item["id"])))
        else:
            await target.answer(text, reply_markup=container_keyboard(str(item["id"])))


async def send_security(target: Message | CallbackQuery) -> None:
    events = list_security_events(10)
    if not events:
        text = "SSH-событий пока нет."
    else:
        rows = ["<b>Последние SSH-события</b>"]
        for event in events:
            rows.append(
                f"{html.escape(event['occurred_at'])} · <b>{html.escape(event['event_type'])}</b> · "
                f"{html.escape(str(event.get('username') or '-'))} · <code>{html.escape(str(event.get('ip') or '-'))}</code>"
            )
        text = "\n".join(rows)

    if isinstance(target, CallbackQuery):
        await target.message.answer(text)
    else:
        await target.answer(text)


async def send_audit(target: Message | CallbackQuery) -> None:
    events = list_audit(10)
    if not events:
        text = "Audit log пока пуст."
    else:
        rows = ["<b>Последние действия</b>"]
        for event in events:
            rows.append(
                f"{html.escape(event['created_at'])} · <b>{html.escape(event['action'])}</b> · "
                f"{html.escape(event['actor'])} · {html.escape(str(event.get('target') or '-'))}"
            )
        text = "\n".join(rows)

    if isinstance(target, CallbackQuery):
        await target.message.answer(text)
    else:
        await target.answer(text)


dp = Dispatcher()


@dp.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


@dp.message(Command("start"))
@admin_only
async def cmd_start(message: Message) -> None:
    add_audit(str(message.from_user.id), "telegram_start", ip=None)
    await message.answer("VPS Admin готов. Выбери действие:", reply_markup=main_keyboard())


@dp.message(Command("status"))
@admin_only
async def cmd_status(message: Message) -> None:
    await message.answer(status_text())


@dp.message(Command("containers"))
@admin_only
async def cmd_containers(message: Message) -> None:
    await send_containers(message)


@dp.message(Command("security"))
@admin_only
async def cmd_security(message: Message) -> None:
    await send_security(message)


@dp.message(Command("audit"))
@admin_only
async def cmd_audit(message: Message) -> None:
    await send_audit(message)


@dp.callback_query(F.data == "status")
@admin_only
async def cb_status(query: CallbackQuery) -> None:
    await query.answer()
    await query.message.answer(status_text(), reply_markup=main_keyboard())


@dp.callback_query(F.data == "containers")
@admin_only
async def cb_containers(query: CallbackQuery) -> None:
    await query.answer()
    await send_containers(query)


@dp.callback_query(F.data == "security")
@admin_only
async def cb_security(query: CallbackQuery) -> None:
    await query.answer()
    await send_security(query)


@dp.callback_query(F.data == "audit")
@admin_only
async def cb_audit(query: CallbackQuery) -> None:
    await query.answer()
    await send_audit(query)


@dp.callback_query(F.data.startswith("logs:"))
@admin_only
async def cb_logs(query: CallbackQuery) -> None:
    await query.answer("Загружаю логи")
    container_id = query.data.split(":", 1)[1]
    logs = docker_collector.logs(container_id, tail=120)
    if len(logs) > 3500:
        logs = logs[-3500:]
    await query.message.answer(f"<b>Logs {html.escape(container_id)}</b>\n<pre>{html.escape(logs or 'Пусто')}</pre>")


@dp.callback_query(F.data.startswith("act:"))
@admin_only
async def cb_action(query: CallbackQuery) -> None:
    _, action, container_id = query.data.split(":", 2)
    docker_collector.action(container_id, action)
    add_audit(str(query.from_user.id), f"telegram_container_{action}", container_id, ip=None)
    await query.answer(f"{action} выполнен", show_alert=True)
    await query.message.answer(f"Контейнер <code>{html.escape(container_id)}</code>: <b>{html.escape(action)}</b> выполнен.")


async def main() -> None:
    init_db()
    if not settings.telegram_bot_token:
        raise RuntimeError("VPS_ADMIN_TELEGRAM_BOT_TOKEN is required")
    if not settings.telegram_admin_id_set:
        logger.warning("VPS_ADMIN_TELEGRAM_ADMIN_IDS is empty. Only /id will work until admin IDs are configured.")

    bot = Bot(settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    monitor_task = None
    if settings.telegram_admin_id_set or os.getenv("VPS_ADMIN_RUN_MONITOR_WITHOUT_ADMINS") == "1":
        monitor_task = asyncio.create_task(Monitor().run_forever())
    try:
        await dp.start_polling(bot)
    finally:
        if monitor_task:
            monitor_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
