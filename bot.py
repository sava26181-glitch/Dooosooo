import asyncio
import logging
import os
import sqlite3
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)
from aiogram.exceptions import TelegramBadRequest
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "bot.db")
PHOTO_PATH = os.getenv("PHOTO_PATH", "bot_photo.jpg")

REPUTATION_URL = "https://t.me/myotzivsaymehere"

CURRENT_RATE_TEXT = """Текущий курс:

Вы продаете:
- От $10 до $100 — 86₽
- От $100 — 87₽

Вы покупаете:
- От $10 до $100 — 91₽
- От $100 — 90₽

Ton, Tron, Solana — напишите интересующую вас монету, и я пришлю вам курс.

Через Bybit НЕ РАБОТАЮ!!"""

dp = Dispatcher()


def db():
    return sqlite3.connect(DB_PATH)


def db_init():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS forwarded_messages (
                admin_message_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS pending_admin_add (
                owner_id INTEGER PRIMARY KEY
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS pending_admin_remove (
                owner_id INTEGER PRIMARY KEY
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS waiting_user_message (
                user_id INTEGER PRIMARY KEY
            )
        """)
        con.commit()


def get_admins():
    with db() as con:
        return [r[0] for r in con.execute("SELECT user_id FROM admins")]


def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in get_admins()


def add_admin(user_id: int):
    with db() as con:
        con.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        con.commit()


def remove_admin(user_id: int):
    with db() as con:
        con.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        con.commit()


def save_forward(admin_message_id: int, user_id: int):
    with db() as con:
        con.execute(
            "INSERT OR REPLACE INTO forwarded_messages "
            "(admin_message_id, user_id) VALUES (?, ?)",
            (admin_message_id, user_id),
        )
        con.commit()


def get_target_user(admin_message_id: int):
    with db() as con:
        row = con.execute(
            "SELECT user_id FROM forwarded_messages WHERE admin_message_id = ?",
            (admin_message_id,),
        ).fetchone()
    return row[0] if row else None


def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Репутация", url=REPUTATION_URL)],
        [InlineKeyboardButton(text="Текущий курс", callback_data="rate")],
        [InlineKeyboardButton(text="Другие услуги", callback_data="services")],
        [InlineKeyboardButton(text="Написать через бота",
                              callback_data="contact")],
    ])


def back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back")]
    ])


def services_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Папка с чатами", callback_data="folder")],
        [InlineKeyboardButton(text="Назад", callback_data="back")],
    ])


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить администратора", callback_data="admin_add")],
        [InlineKeyboardButton(text="Удалить администратора", callback_data="admin_remove")],
        [InlineKeyboardButton(text="Список администраторов", callback_data="admin_list")],
    ])


async def send_photo_or_text(bot: Bot, chat_id: int, text: str, keyboard=None):
    # Фото отключено: меню и все разделы отправляются только текстом с кнопками.
    await bot.send_message(chat_id, text, reply_markup=keyboard)


START_TEXT = """Добро пожаловать.

Здесь вы можете ознакомиться с моей репутацией, узнать актуальный курс и ознакомиться с доступными услугами. Вы можете написать мне в случае спамблока"""


@dp.message(CommandStart())
async def start(message: Message, bot: Bot):
    await send_photo_or_text(bot, message.chat.id, START_TEXT, main_keyboard())


@dp.callback_query(F.data == "back")
async def back(callback, bot: Bot):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await send_photo_or_text(bot, callback.message.chat.id, START_TEXT, main_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "rate")
async def rate(callback, bot: Bot):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await send_photo_or_text(bot, callback.message.chat.id, CURRENT_RATE_TEXT, back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "services")
async def services(callback, bot: Bot):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await send_photo_or_text(
        bot,
        callback.message.chat.id,
        "Другие услуги",
        services_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "folder")
async def folder(callback, bot: Bot):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await send_photo_or_text(
        bot,
        callback.message.chat.id,
        "Папка с 80+ чатов услуг\nкупить - @by_asterr",
        back_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "contact")
async def contact(callback, bot: Bot):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    with db() as con:
        con.execute(
            "INSERT OR REPLACE INTO waiting_user_message (user_id) VALUES (?)",
            (callback.from_user.id,),
        )
        con.commit()

    await send_photo_or_text(
        bot,
        callback.message.chat.id,
        "Введите ваше сообщение и мы напишем вам как можно скорее.",
        back_keyboard(),
    )
    await callback.answer()


# ---------- СКРЫТАЯ ПАНЕЛЬ ВЛАДЕЛЬЦА ----------
@dp.message(Command("panel"))
async def hidden_admin_panel(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    await message.answer(
        "Панель управления",
        reply_markup=admin_keyboard(),
    )


@dp.callback_query(F.data == "admin_add")
async def admin_add_start(callback):
    if callback.from_user.id != OWNER_ID:
        await callback.answer()
        return

    with db() as con:
        con.execute(
            "INSERT OR REPLACE INTO pending_admin_add (owner_id) VALUES (?)",
            (OWNER_ID,),
        )
        con.commit()

    await callback.message.answer(
        "Отправьте числовой Telegram ID пользователя, которого хотите добавить в администраторы."
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_remove")
async def admin_remove_start(callback):
    if callback.from_user.id != OWNER_ID:
        await callback.answer()
        return

    await callback.message.answer(
        "Отправьте числовой Telegram ID администратора, которого хотите удалить."
    )
    with db() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS pending_admin_remove (owner_id INTEGER PRIMARY KEY)"
        )
        con.execute(
            "INSERT OR REPLACE INTO pending_admin_remove (owner_id) VALUES (?)",
            (OWNER_ID,),
        )
        con.commit()
    await callback.answer()


@dp.callback_query(F.data == "admin_list")
async def admin_list(callback):
    if callback.from_user.id != OWNER_ID:
        await callback.answer()
        return

    admins = get_admins()
    text = "Администраторы:\n\n"
    if not admins:
        text += "Дополнительных администраторов нет."
    else:
        text += "\n".join(f"ID: {x}" for x in admins)

    await callback.message.answer(text)
    await callback.answer()


# ---------- ОТВЕТЫ АДМИНОВ ----------
@dp.message(F.reply_to_message)
async def admin_reply(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    target = get_target_user(message.reply_to_message.message_id)
    if not target:
        return

    try:
        await bot.copy_message(
            chat_id=target,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
        await message.answer("Ответ отправлен.")
    except TelegramBadRequest:
        await message.answer("Не удалось отправить ответ пользователю.")


# ---------- СКРЫТАЯ ПАНЕЛЬ: ОБРАБОТКА ID ----------
@dp.message()
async def all_messages(message: Message, bot: Bot):
    uid = message.from_user.id

    if uid == OWNER_ID:
        with db() as con:
            remove_pending = con.execute(
                "SELECT 1 FROM pending_admin_remove WHERE owner_id = ?",
                (OWNER_ID,),
            ).fetchone()

            add_pending = con.execute(
                "SELECT 1 FROM pending_admin_add WHERE owner_id = ?",
                (OWNER_ID,),
            ).fetchone()

        if message.text and message.text.isdigit():
            target_id = int(message.text)

            if add_pending:
                add_admin(target_id)
                with db() as con:
                    con.execute("DELETE FROM pending_admin_add WHERE owner_id = ?", (OWNER_ID,))
                    con.commit()
                await message.answer(f"Администратор {target_id} добавлен.")
                return

            if remove_pending:
                remove_admin(target_id)
                with db() as con:
                    con.execute("DELETE FROM pending_admin_remove WHERE owner_id = ?", (OWNER_ID,))
                    con.commit()
                await message.answer(f"Администратор {target_id} удалён.")
                return

        return

    if is_admin(uid):
        return

    if message.text and message.text.startswith("/"):
        return

    with db() as con:
        waiting = con.execute(
            "SELECT 1 FROM waiting_user_message WHERE user_id = ?",
            (uid,),
        ).fetchone()

    if not waiting:
        return

    admins = get_admins()
    recipients = list(dict.fromkeys([OWNER_ID] + admins))

    for admin_id in recipients:
        try:
            forwarded = await bot.forward_message(
                chat_id=admin_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            save_forward(forwarded.message_id, uid)

            username = f"@{message.from_user.username}" if message.from_user.username else "—"

            await bot.send_message(
                admin_id,
                "Новое сообщение\n\n"
                f"ID: {uid}\n"
                f"Имя: {message.from_user.full_name}\n"
                f"Username: {username}\n\n"
                "Ответьте через Reply на пересланное сообщение.",
            )
        except Exception:
            logging.exception("Не удалось отправить сообщение админу %s", admin_id)

    with db() as con:
        con.execute(
            "DELETE FROM waiting_user_message WHERE user_id = ?",
            (uid,),
        )
        con.commit()

    await send_photo_or_text(bot, message.chat.id, START_TEXT, main_keyboard())


WEBHOOK_PATH = "/telegram/webhook"


def get_webhook_url():
    configured = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
    if configured:
        if configured.endswith(WEBHOOK_PATH):
            return configured
        return configured + WEBHOOK_PATH

    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if render_url:
        return render_url + WEBHOOK_PATH

    raise RuntimeError(
        "Не задан WEBHOOK_URL и не найден RENDER_EXTERNAL_URL. "
        "Для Render укажите WEBHOOK_URL=https://ваш-сервис.onrender.com/telegram/webhook"
    )


async def on_startup(bot: Bot):
    webhook_url = get_webhook_url()
    await bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=False,
    )
    logging.info("Telegram webhook set: %s", webhook_url)


async def on_shutdown(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=False)
    await bot.session.close()


async def health_check(request):
    return web.Response(text="OK")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN")
    if not OWNER_ID:
        raise RuntimeError("Не задан OWNER_ID")

    logging.basicConfig(level=logging.INFO)
    db_init()

    bot = Bot(BOT_TOKEN)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    app.router.add_get("/", health_check)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)

    port = int(os.getenv("PORT", "10000"))
    logging.info("Starting webhook server on 0.0.0.0:%s", port)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logging.info("Webhook server is listening on port %s", port)

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
