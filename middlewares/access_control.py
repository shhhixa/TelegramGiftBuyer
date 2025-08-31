"""
Модуль middleware для контроля доступа.

Этот модуль содержит классы и функции для:
- Ограничения доступа к боту только для разрешённых пользователей.
- Отображения гостевого меню для неразрешённых пользователей.

Основные классы и функции:
- AccessControlMiddleware: Middleware для проверки доступа.
- show_guest_menu: Показывает гостевое меню.
"""

# --- Стандартные библиотеки ---
import logging

# --- Сторонние библиотеки ---
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)

class AccessControlMiddleware(BaseMiddleware):
    """
    Мидлварь доступа: разрешает работу только определённым user_id.
    Отклоняет все остальные запросы.
    """
    FREE_CALLBACKS = {"guest_deposit_menu"}
    FREE_STATES = {"ConfigWizard:guest_deposit_amount"}

    def __init__(self, allowed_user_ids: list[int]) -> None:
        """
        :param allowed_user_ids: Список разрешённых user_id.
        :param bot: Экземпляр бота.
        """
        self.allowed_user_ids = allowed_user_ids
        super().__init__()

    async def __call__(self, handler: callable, event: TelegramObject, data: dict) -> None:
        """
        Проверяет наличие пользователя в списке разрешённых.
        При отказе отправляет уведомление и блокирует обработку.
        """
        user = data.get("event_from_user")
        if user and user.id not in self.allowed_user_ids:
            # Разрешить нажатие кнопки пополнения
            if isinstance(event, CallbackQuery) and getattr(event, "data", None) in self.FREE_CALLBACKS:
                return await handler(event, data)
            # Разрешить оплату (состояние FSM)
            fsm_state = data.get("state")
            if fsm_state:
                state_name = await fsm_state.get_state()
                if state_name in self.FREE_STATES:
                    return await handler(event, data)
            # Разрешить сообщения-инвойсы (invoice)
            if isinstance(event, Message):
                if getattr(event, "invoice", None) or getattr(event, "successful_payment", None):
                    return await handler(event, data)
            # Всё остальное запрещаем
            try:
                if isinstance(event, Message):
                    await show_guest_menu(event)
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔️ Нет доступа", show_alert=True)
            except Exception as e:
                logger.error(f"Не удалось отправить отказ пользователю {user.id}: {e}")
            return
        return await handler(event, data)
    
async def show_guest_menu(message: Message) -> None:
    """
    Показывает гостевое меню для неразрешённых пользователей.
    """
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 Пополнить", callback_data="guest_deposit_menu")
            ]
        ]
    )
    await message.answer(
        "✅ Вы можете <b>получать подарки</b> от этого бота.\n"
        "💰 Вы можете <b>пополнить</b> звёзды в бот.\n"
        "⛔️ У вас <b>нет доступа</b> к панели управления.\n\n"
        "<b>🤖 Исходный код: <a href=\"https://github.com/leozizu/TelegramGiftsBot\">GitHub</a></b>\n"
        "<b>🐸 Автор: @leozizu</b>\n<b>📢 Канал: @pepeksey</b>",
        reply_markup=kb
    )