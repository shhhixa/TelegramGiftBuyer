"""
Модуль управления меню Telegram бота.

Этот модуль содержит функции для:
- Генерации inline-клавиатур для меню.
- Обновления, отправки и удаления меню в чате.
- Сохранения и получения ID последнего сообщения меню.

Основные функции:
- update_menu: Обновляет меню в чате.
- send_menu: Отправляет новое меню в чат.
- delete_menu: Удаляет предыдущее меню.
- config_action_keyboard: Генерирует клавиатуру для действий в меню.
- payment_keyboard: Генерирует клавиатуру для оплаты.
"""

# --- Сторонние библиотеки ---
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- Внутренние библиотеки ---
from services.config import load_config, save_config, get_valid_config, format_config_summary

async def update_last_menu_message_id(message_id: int) -> None:
    """
    Сохраняет id последнего сообщения с меню в конфиг.
    :param message_id: ID сообщения меню
    """
    config = await load_config()
    config["LAST_MENU_MESSAGE_ID"] = message_id
    await save_config(config)


async def get_last_menu_message_id() -> int | None:
    """
    Возвращает id последнего отправленного сообщения меню.
    :return: ID сообщения или None
    """
    config = await load_config()
    return config.get("LAST_MENU_MESSAGE_ID")


def config_action_keyboard(active: bool) -> InlineKeyboardMarkup:
    """
    Генерирует inline-клавиатуру для меню с действиями.
    :param active: Статус активности (True/False)
    :return: InlineKeyboardMarkup для меню
    """
    toggle_text = "🔴 Выключить" if active else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=toggle_text, callback_data="toggle_active"),
            InlineKeyboardButton(text="✏️ Профили", callback_data="profiles_menu")
        ],
        [
            InlineKeyboardButton(text="♻️ Сбросить", callback_data="reset_bought"),
            InlineKeyboardButton(text="⚙️ Юзербот", callback_data="userbot_menu")
        ],
        [
            InlineKeyboardButton(text="💰 Пополнить", callback_data="deposit_menu"),
            InlineKeyboardButton(text="↩️ Вывести", callback_data="refund_menu")
        ],
        [
            InlineKeyboardButton(text="🎏 Каталог", callback_data="catalog"),
            InlineKeyboardButton(text="❓ Помощь", callback_data="show_help")
        ],
        [
            InlineKeyboardButton(text="📄 Логи", callback_data="log")
        ]
    ])


async def update_menu(bot: Bot, chat_id: int, user_id: int, message_id: int) -> None:
    """
    Обновляет меню в чате: удаляет предыдущее и отправляет новое.
    :param bot: Экземпляр бота aiogram
    :param chat_id: ID чата
    :param user_id: ID пользователя
    :param message_id: ID текущего сообщения меню
    """
    config = await get_valid_config(user_id)
    await delete_menu(bot=bot, chat_id=chat_id, current_message_id=message_id)
    await send_menu(bot=bot, chat_id=chat_id, config=config, text=format_config_summary(config, user_id))


async def delete_menu(bot: Bot, chat_id: int, current_message_id: int = None) -> None:
    """
    Удаляет последнее сообщение с меню, если оно отличается от текущего.
    :param bot: Экземпляр бота aiogram
    :param chat_id: ID чата
    :param current_message_id: ID текущего сообщения меню
    """
    last_menu_message_id = await get_last_menu_message_id()
    if last_menu_message_id and last_menu_message_id != current_message_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=last_menu_message_id)
        except TelegramBadRequest as e:
            error_text = str(e)
            if "message can't be deleted for everyone" in error_text:
                await bot.send_message(
                    chat_id,
                    "⚠️ Предыдущее меню устарело и не может быть удалено (прошло более 48 часов). Используйте актуальное меню.\n"
                )
            elif "message to delete not found" in error_text:
                pass
            else:
                raise


async def send_menu(bot: Bot, chat_id: int, config: dict, text: str) -> int:
    """
    Отправляет новое меню в чат и обновляет id последнего сообщения.
    :param bot: Экземпляр бота aiogram
    :param chat_id: ID чата
    :param config: Словарь конфигурации
    :param text: Текст меню
    :return: ID отправленного сообщения
    """
    sent = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=config_action_keyboard(config.get("ACTIVE"))
    )
    await update_last_menu_message_id(sent.message_id)
    return sent.message_id


def payment_keyboard(amount: int) -> InlineKeyboardMarkup:
    """
    Генерирует inline-клавиатуру с кнопкой оплаты для инвойса.
    :param amount: Сумма для пополнения
    :return: InlineKeyboardMarkup с кнопкой оплаты
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Пополнить ★{amount:,}", pay=True)
    return builder.as_markup()