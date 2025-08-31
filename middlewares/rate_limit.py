"""
Модуль middleware для ограничения частоты выполнения команд и нажатий.

Этот модуль содержит классы и функции для:
- Защиты от спама через ограничение частоты вызовов.
- Игнорирования ограничений для разрешённых пользователей.

Основные классы и функции:
- RateLimitMiddleware: Middleware для ограничения частоты выполнения команд.
"""

# --- Стандартные библиотеки ---
import time
import logging

# --- Сторонние библиотеки ---
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, CallbackQuery

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseMiddleware):
    """
    Middleware для защиты от спама: ограничивает частоту выполнения команд и нажатий на кнопки.
    Применимо как к текстовым сообщениям (Message), так и к CallbackQuery.

    Ограничение действует отдельно для каждой команды и пользователя.
    Пользователи из списка allowed_user_ids не ограничиваются.
    """
    def __init__(self, commands_limits: dict = None, allowed_user_ids: list[int] = None) -> None:
        """
        :param commands_limits: Словарь с лимитами в формате {команда: интервал_в_секундах}
        :param allowed_user_ids: Список user_id, которым разрешено игнорировать ограничения
        """
        self.last_times = {}  # user_id -> {command: timestamp}
        self.commands_limits = commands_limits or {}  # command: seconds
        self.allowed_user_ids = allowed_user_ids or []

    async def __call__(self, handler: callable, event: TelegramObject, data: dict) -> None:
        """
        Основной метод мидлвари: проверяет частоту вызовов команд/кнопок.
        Если превышен лимит — сообщение/запрос игнорируется и пользователю отправляется предупреждение.
        """
        now = time.monotonic()
        user_id = None
        command = None

        if isinstance(event, Message):
            user_id = event.from_user.id
            command = event.text.split()[0] if event.text else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            command = event.data

        if user_id is None or command is None:
            return await handler(event, data)

        if user_id in self.allowed_user_ids:
            return await handler(event, data)

        for cmd, limit in self.commands_limits.items():
            if command == cmd:
                user_times = self.last_times.setdefault(user_id, {})
                last = user_times.get(cmd, 0)

                if now - last < limit:
                    if isinstance(event, Message):
                        await event.answer("⏳ Не спамьте, пожалуйста. Попробуйте чуть позже.")
                    elif isinstance(event, CallbackQuery):
                        await event.answer("⏳ Не спамьте, пожалуйста.", show_alert=True)
                    return
                user_times[cmd] = now

        return await handler(event, data)