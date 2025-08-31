"""
Модуль основных хендлеров для главного меню Telegram-бота.

Этот модуль содержит функции для:
- Обработки команды /start.
- Переходов по главным кнопкам меню.
- Отправки справки по работе с ботом.
- Тестовой покупки подарка.
- Сброса профилей и переключения статуса активности.
- Обработки платежей и успешных оплат.

Основные функции:
- command_status_handler: Обрабатывает команду /start.
- start_callback: Переход в главное меню.
- help_callback: Отправляет справку по работе с ботом.
- buy_test_gift: Выполняет тестовую покупку подарка.
- reset_bought_callback: Сбрасывает счетчики купленных подарков.
- toggle_active_callback: Переключает статус активности.
- pre_checkout_handler: Обрабатывает событие предоплаты.
- process_successful_payment: Обрабатывает успешное завершение оплаты.
"""

# --- Сторонние библиотеки ---
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext

# --- Внутренние модули ---
from services.config import get_valid_config, save_config, format_config_summary, get_allowed_users
from services.menu import update_menu, config_action_keyboard 
from services.balance import refresh_balance
from services.buy_bot import buy_gift
from services.buy_userbot import buy_gift_userbot
from middlewares.access_control import show_guest_menu
from utils.log_cache import get_cached_text

def register_main_handlers(dp: Dispatcher, bot: Bot, version: str) -> None:
    """
    Регистрирует все основные обработчики событий для главного меню Telegram-бота.
    Включает обработку команд /start, переходов по главным кнопкам, справку, тестовую покупку, сброс профилей, переключение статуса, обработку платежей и успешных оплат.
    Все обработчики добавляются в диспетчер dp.
    """

    @dp.message(CommandStart())
    async def command_status_handler(message: Message, state: FSMContext) -> None:
        """
        Обрабатывает команду /start от пользователя.
        Проверяет права пользователя, очищает все состояния FSM, обновляет баланс и отображает главное меню с актуальной информацией.
        Если пользователь не авторизован — показывает гостевое меню.
        """
        allowed_user_ids = get_allowed_users()
        if message.from_user.id not in allowed_user_ids:
            await show_guest_menu(message)
            return
        
        await state.clear()
        await refresh_balance(bot)
        await update_menu(bot=bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)


    @dp.callback_query(F.data == "main_menu")
    async def start_callback(call: CallbackQuery, state: FSMContext) -> None:
        """
        Обрабатывает нажатие на кнопку "Меню" в интерфейсе бота.
        Очищает все состояния FSM пользователя, обновляет баланс и отображает главное меню с актуальными данными профиля.
        """
        await state.clear()
        await call.answer()
        config = await get_valid_config(call.from_user.id)
        await refresh_balance(call.bot)
        await update_menu(
            bot=call.bot,
            chat_id=call.message.chat.id,
            user_id=call.from_user.id,
            message_id=call.message.message_id
        )


    @dp.callback_query(F.data == "show_help")
    async def help_callback(call: CallbackQuery) -> None:
        """
        Отправляет пользователю подробную справку по работе с ботом.
        В справке описаны основные функции, подсказки по работе с профилями, пополнением, возвратом, а также тестовая покупка подарка.
        К справке добавляются кнопки для тестовой покупки и возврата в главное меню.
        """
        target_display = f"<code>{call.from_user.id} - @{call.from_user.username}</code> (Вы)"
        bot_info = await call.bot.get_me()
        bot_username = bot_info.username
        help_text = (
            f"<b>🛠 Управление ботом <code>v{version}</code> :</b>\n\n"
            "<b>🟢 Включить / 🔴 Выключить</b> — запускает или останавливает покупки.\n"
            "<b>✏️ Профили</b> — Добавление и удаление профилей с конфигурациями для покупки подарков.\n"
            "<b>♻️ Сбросить</b> — обнуляет количество уже купленных подарков для всех профилей, чтобы не создавать снова такие же профили.\n"
            "<b>⚙️ Юзербот</b> — управление сессией Telegram-аккаунта.\n"
            "<b>💰 Пополнить</b> — депозит звёзд в бот (можно запретить или разрешить пополнение бота с других аккаунтов).\n"
            "<b>↩️ Вывести</b> — возврат звёзд по ID транзакции или вывести все звёзды сразу по команде /withdraw_all.\n"
            "<b>🎏 Каталог</b> — список доступных к покупке подарков в маркете.\n\n"
            "<b>📌 Подсказки:</b>\n\n"
            f"❗️ Если получатель подарка — другой пользователь, он должен зайти в этот бот <code>@{bot_username}</code> и нажать <code>/start</code>.\n"
            "❗️ Получатель подарка <b>аккаунт</b> — пишите <b>id</b> пользователя (узнать id можно тут @userinfobot).\n"
            "❗️ Получатель подарка <b>канал</b> — пишите <b>username</b> канала.\n"
            "❗️ Если подарок отправляется <b>через Юзербота</b>, указывайте <b>только username</b> получателя — независимо от того, это пользователь или канал.\n"
            "❗️ Чтобы аккаунт <b>Юзербота</b> отправил подарок на другой аккаунт, между аккаунтами должна быть переписка.\n"
            f"❗️ Чтобы пополнить баланс бота с любого аккаунта, зайдите в этот бот <code>@{bot_username}</code> и нажмите <code>/start</code>, чтобы вызвать меню пополнения.\n"
            "❗️ Как посмотреть <b>ID транзакции</b> для возврата звёзд?  Нажмите на сообщение об оплате в чате с ботом и там будет ID транзакции.\n"
            f"❗️ Хотите протестировать бот? Купите подарок 🧸 за ★15 c баланса <b>Бота</b> или <b>Юзербота</b>, получатель {target_display}.\n\n"
            "<b>🐸 Автор: @leozizu</b>\n"
            "<b>📢 Канал: @pepeksey</b>"
        )
        button = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Тест? Купить 🧸 за ★15 — Бот", callback_data="buy_test_gift")],
            [InlineKeyboardButton(text="Тест? Купить 🧸 за ★15 — Юзербот", callback_data="buy_test_gift_userbot")],
            [InlineKeyboardButton(text="☰ Меню", callback_data="main_menu")]
        ])
        await call.answer()
        await call.message.answer(help_text, reply_markup=button)

    
    @dp.callback_query(F.data == "show_userbot_help")
    async def userbot_help_callback(call: CallbackQuery) -> None:
        """
        Отправляет справку по подключению и использованию Telegram-юзербота.
        Описывает пошагово процесс получения api_id и api_hash, ограничения Telegram, рекомендации по безопасности.
        К сообщению добавляются кнопки для перехода к меню юзербота и возврата в главное меню.
        """
        help_text = (
            "🔐 <b>Как получить api_id и api_hash для Telegram аккаунта:</b>\n\n"
            "┌1️⃣ Перейдите на сайт: <a href=\"https://my.telegram.org\">https://my.telegram.org</a>\n"
            "├2️⃣ Войдите, указав номер телефона и код из Telegram\n"
            "├3️⃣ Выберите: <code>API development tools</code>\n"
            "├4️⃣ Введите <code>App title</code> (например: <code>GiftApp</code>)\n"
            "├5️⃣ Укажите <code>Short name</code> (любое короткое имя)\n"
            "└6️⃣ После этого вы получите:\n"
            "    ├🔸 <b>App api_id</b> (число)\n"
            "    └🔸 <b>App api_hash</b> (набор символов)\n\n"
            "📥 Эти данные вводятся при подключении юзербота.\n\n"
            "📍 <b>Важно:</b> После создания <b>api_id</b> и <b>api_hash</b> может потребоваться "
            "подождать 2–3 дня — это нормальное ограничение Telegram!\n\n"
            "⚠️ Не передавайтe <b>api_id</b> и <b>api_hash</b> другим людям!"
        )
        button = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⚙️ Юзербот", callback_data="userbot_menu"),
            InlineKeyboardButton(text="☰ Меню", callback_data="userbot_main_menu")
        ]])
        await call.answer()
        await call.message.answer(help_text, reply_markup=button, disable_web_page_preview=True)


    @dp.callback_query(F.data == "buy_test_gift")
    async def buy_test_gift(call: CallbackQuery) -> None:
        """
        Обрабатывает тестовую покупку подарка (🧸 за ★15) для проверки работы бота.
        Использует ваш профиль пользователя, проверяет баланс и корректность получателя.
        В случае успеха — отправляет сообщение о покупке и обновляет меню, иначе — сообщает о невозможности покупки и причинах.
        """
        gift_id = '5170233102089322756'
        user_id = call.from_user.id
        username = call.from_user.username
        target_display = f"<code>{user_id} - @{username}</code> (Вы)"

        success = await buy_gift(
            bot=call.bot,
            env_user_id=call.from_user.id,
            gift_id=gift_id,
            target_user_id=user_id,
            target_chat_id=None,
            gift_price=15,
            file_id=None
        )
        if not success:
            await call.answer()
            await call.message.answer("⚠️ Покупка подарка 🧸 за ★15 невозможна.\n"
                                      "💰 Пополните баланс! Проверьте адрес получателя!\n"
                                      "🪜 Проверьте типы принимаемых подарков у получателя!\n"
                                      "🚦 Статус изменён на 🔴 (неактивен).")
            await update_menu(bot=bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)
            return

        await call.answer()
        await call.message.answer(f"✅ Подарок 🧸 за ★15 куплен. Получатель: {target_display}.")
        await update_menu(bot=bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


    @dp.callback_query(F.data == "buy_test_gift_userbot")
    async def buy_test_gift_userbot(call: CallbackQuery) -> None:
        """
        Обрабатывает тестовую покупку подарка (🧸 за ★15) для проверки работы Юзербота.
        Использует ваш профиль пользователя, проверяет баланс и корректность получателя.
        В случае успеха — отправляет сообщение о покупке и обновляет меню, иначе — сообщает о невозможности покупки и причинах.
        """
        gift_id = '5170233102089322756'
        user_id = call.from_user.id
        username = call.from_user.username
        target_display = f"<code>{user_id} - @{username}</code> (Вы)"

        success = await buy_gift_userbot(
            session_user_id=user_id,
            gift_id=gift_id,
            target_user_id=None,
            target_chat_id=f"@{username}",
            gift_price=15,
            file_id=None
        )
        if not success:
            await call.answer()
            await call.message.answer("⚠️ Покупка подарка 🧸 за ★15 невозможна.\n"
                                      "💰 Пополните баланс! Проверьте адрес получателя!\n"
                                      "🪜 Проверьте типы принимаемых подарков у получателя!\n"
                                      "🚦 Статус изменён на 🔴 (неактивен).")
            await update_menu(bot=bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)
            return

        await call.answer()
        await call.message.answer(f"✅ Подарок 🧸 за ★15 куплен. Получатель: {target_display}.")
        await update_menu(bot=bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


    @dp.callback_query(F.data == "reset_bought")
    async def reset_bought_callback(call: CallbackQuery) -> None:
        """
        Сбрасывает счетчики купленных подарков, потраченных звёзд и статусов выполнения для всех профилей пользователя.
        Отключает активность профиля, сохраняет изменения и обновляет интерфейс с актуальной информацией.
        В случае ошибки редактирования сообщения — обрабатывает исключение TelegramBadRequest.
        """
        config = await get_valid_config(call.from_user.id)
        # Сбросить счетчики во всех профилях
        for profile in config["PROFILES"]:
            profile["BOUGHT"] = 0
            profile["SPENT"] = 0
            profile["DONE"] = False
        config["ACTIVE"] = False
        await save_config(config)
        info = format_config_summary(config, call.from_user.id)
        try:
            await call.message.edit_text(
                info,
                reply_markup=config_action_keyboard(config["ACTIVE"])
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise
        await call.answer("Счётчик покупок сброшен.")


    @dp.callback_query(F.data == "toggle_active")
    async def toggle_active_callback(call: CallbackQuery) -> None:
        """
        Переключает статус активности бота для пользователя (активен/неактивен).
        Сохраняет изменения, обновляет интерфейс и отправляет пользователю уведомление о смене статуса.
        """
        config = await get_valid_config(call.from_user.id)
        config["ACTIVE"] = not config.get("ACTIVE", False)
        await save_config(config)
        info = format_config_summary(config, call.from_user.id)
        await call.message.edit_text(
            info,
            reply_markup=config_action_keyboard(config["ACTIVE"])
        )
        await call.answer("Статус обновлён")


    @dp.callback_query(F.data == "log")
    async def send_logs_callback(call: CallbackQuery) -> None:
        """Отправка последних кэшированных логов пользователю."""
        await call.answer()
        try:
            text = get_cached_text()
            if not text:
                await call.message.answer("⚠️ Логи пусты.")
                return
            # Лимит на размер сообщения Telegram: оставляем хвост логов, затем экранируем
            max_chars = 3800
            if len(text) > max_chars:
                # Обрезаем текст по последнему переходу на новую строку
                text = text[-max_chars:]
                first_newline = text.find('\n')
                if first_newline != -1 and first_newline < len(text):
                    text = text[first_newline + 1:]
            header = "📄 Логи (последние {} строк):\n".format(text.count("\n") + 1)
            await call.message.answer(f"{header}<pre>{text}</pre>")
            await update_menu(bot=bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)
        except Exception as e:
            await call.message.answer(f"Ошибка при получении логов: {e}")


    @dp.pre_checkout_query()
    async def pre_checkout_handler(pre_checkout_query) -> None:
        """
        Обрабатывает событие предоплаты (pre_checkout_query) при оплате через Telegram Invoice.
        Подтверждает готовность к оплате, чтобы Telegram мог завершить транзакцию.
        """
        await pre_checkout_query.answer(ok=True)


    @dp.message(F.successful_payment)
    async def process_successful_payment(message: Message) -> None:
        """
        Обрабатывает успешное завершение оплаты через Telegram Invoice.
        Если пользователь не авторизован — отправляет инструкцию по возврату средств владельцу бота и показывает гостевое меню.
        Для авторизованных пользователей — обновляет баланс и главное меню, отправляет сообщение о пополнении.
        """
        allowed_user_ids = get_allowed_users()
        if message.from_user.id not in allowed_user_ids:
            transaction_id = message.successful_payment.telegram_payment_charge_id
            user_id = message.from_user.id
            bot_user = await message.bot.get_me()
            await message.answer(
                f"✅ Баланс успешно пополнен.\n\n"
                f"Для возврата владелец бота @{bot_user.username} должен запустить команду:\n\n"
                f"<code>/refund {user_id} {transaction_id}</code>",
                message_effect_id="5104841245755180586"
            )
            await show_guest_menu(message)
            return
        
        await message.answer(
            f'✅ Баланс успешно пополнен.',
            message_effect_id="5104841245755180586"
        )
        balance = await refresh_balance(bot)
        await update_menu(bot=bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
