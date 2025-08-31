"""
Модуль хендлеров для пошагового редактирования конфигурации (FSM Wizard).

Этот модуль содержит функции для:
- Управления состояниями FSM для редактирования конфигурации.
- Обработки ввода данных для профилей и userbot.
- Формирования и обновления меню управления профилями и userbot.
- Подключения, отключения и удаления userbot-сессий.

Основные функции:
- userbot_menu: Формирует меню управления userbot.
- profiles_menu: Показывает меню управления профилями.
- on_userbot_menu: Обрабатывает колбэк для меню userbot.
- confirm_userbot_delete: Запрашивает подтверждение удаления userbot.
- userbot_enable_handler: Включает userbot.
- userbot_disable_handler: Отключает userbot.
- init_userbot_handler: Запускает процесс подключения userbot.
- get_api_id: Обрабатывает ввод api_id.
- get_api_hash: Обрабатывает ввод api_hash.
- get_phone: Сохраняет номер телефона для userbot.
- get_code: Обрабатывает код подтверждения.
- get_password: Завершает авторизацию userbot.
- on_profiles_menu: Открывает меню управления профилями.
- profile_text: Формирует текстовое описание параметров профиля.
- profile_edit_keyboard: Создаёт клавиатуру для редактирования профиля.
- on_profile_edit: Открывает экран редактирования профиля.
- on_profile_name_entered: Обрабатывает ввод нового имени профиля.
- edit_profile_min_price: Изменяет минимальную цену подарков.
- edit_profile_min_supply: Изменяет минимальный supply подарков.
- edit_profile_limit: Изменяет лимит звёзд для профиля.
- edit_profile_count: Изменяет количество подарков в профиле.
- edit_profile_target: Изменяет получателя подарков.
"""

# --- Стандартные библиотеки ---
import logging

# --- Сторонние библиотеки ---
from aiogram import Router, F, Bot, Dispatcher
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import Message, CallbackQuery, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError

# --- Внутренние модули ---
from services.config import get_valid_config, get_target_display, save_config, get_deposit_enabled
from services.menu import update_menu, payment_keyboard
from services.balance import refresh_balance, refund_all_star_payments
from services.config import CURRENCY, MAX_PROFILES, DEVICE_MODELS, SYSTEM_VERSIONS, APP_VERSIONS, add_profile, remove_profile, update_profile, get_allowed_users
from services.userbot import is_userbot_active, is_userbot_premium, userbot_send_self, delete_userbot_session, start_userbot, continue_userbot_signin, finish_userbot_signin, RESTART_REQUIRED
from middlewares.access_control import show_guest_menu
from utils.misc import now_str, is_valid_profile_name, PHONE_REGEX, API_HASH_REGEX

logger = logging.getLogger(__name__)
wizard_router = Router()


class ConfigWizard(StatesGroup):
    """
    Класс состояний для FSM wizard (пошаговое редактирование конфигурации).
    Каждый state — отдельный шаг процесса.
    """
    min_price = State()
    max_price = State()
    min_supply = State()
    max_supply = State()
    count = State()
    limit = State()
    user_id = State()
    edit_min_price = State()
    edit_max_price = State()
    edit_min_supply = State()
    edit_max_supply = State()
    edit_count = State()
    edit_limit = State()
    edit_user_id = State()
    edit_gift_sender = State()
    gift_sender = State()
    edit_profile_name = State()
    deposit_amount = State()
    refund_id = State()
    guest_deposit_amount = State()
    userbot_api_id = State()
    userbot_api_hash = State()
    userbot_phone = State()
    userbot_code = State()
    userbot_password = State()


def create_digit_keyboard() -> InlineKeyboardMarkup:
    """Создаёт инлайн-клавиатуру с цифрами для ввода кода."""
    builder = InlineKeyboardBuilder()
    buttons = [
        InlineKeyboardButton(text='1️⃣', callback_data='code_1'),
        InlineKeyboardButton(text='2️⃣', callback_data='code_2'),
        InlineKeyboardButton(text='3️⃣', callback_data='code_3'),
        InlineKeyboardButton(text='4️⃣', callback_data='code_4'),
        InlineKeyboardButton(text='5️⃣', callback_data='code_5'),
        InlineKeyboardButton(text='6️⃣', callback_data='code_6'),
        InlineKeyboardButton(text='7️⃣', callback_data='code_7'),
        InlineKeyboardButton(text='8️⃣', callback_data='code_8'),
        InlineKeyboardButton(text='9️⃣', callback_data='code_9'),
        InlineKeyboardButton(text='⬅️', callback_data='code_delete'),
        InlineKeyboardButton(text='0️⃣', callback_data='code_0'),
        InlineKeyboardButton(text='🆗', callback_data='code_enter')
    ]
    builder.add(*buttons)
    builder.adjust(3)
    return builder.as_markup()


@wizard_router.callback_query(F.data == "userbot_menu")
async def on_userbot_menu(call: CallbackQuery):
    """
    Вызывает обновление меню userbot'а после колбэка.
    """
    await userbot_menu(call.message, call.from_user.id)
    await call.answer()


@wizard_router.callback_query(F.data == "userbot_menu_edit")
async def on_userbot_menu_edit(call: CallbackQuery):
    """
    Вызывает обновление меню userbot'а после колбэка.
    """
    await userbot_menu(call.message, call.from_user.id, True)
    await call.answer()


async def userbot_menu(message: Message, user_id: int, edit: bool = False) -> None:
    """
    Формирует и отправляет (или редактирует) меню управления userbot'ом для пользователя.

    Аргументы:
    - message: Объект сообщения, к которому прикрепляется меню.
    - user_id: ID пользователя, для которого формируется меню.
    - edit: Если True, меню редактируется, иначе отправляется новое.
    """
    config = await get_valid_config(user_id)
    userbot = config.get("USERBOT", {})

    userbot_interval = userbot.get("UPDATE_INTERVAL")
    userbot_username = userbot.get("USERNAME")
    userbot_user_id = userbot.get("USER_ID")
    phone = userbot.get("PHONE")
    enabled = userbot.get("ENABLED", False)

    if is_userbot_active(user_id):
        is_premium = await is_userbot_premium(user_id)
        status_button = InlineKeyboardButton(
            text="🔕 Выключить" if enabled else "🔔 Включить",
            callback_data="userbot_disable" if enabled else "userbot_enable"
        )
        text = (
            "✅ <b>Юзербот подключён.</b>\n\n"
            f"┌ <b>Пользователь:</b> {'@' + userbot_username if userbot_username else '—'} (<code>{userbot_user_id}</code>)\n"
            f"├ <b>Номер:</b> <code>{phone or '—'}</code>\n"
            f"├ <b>Статус:</b> {'🔔 Включён ' if enabled else '🔕 Выключен'}\n"
            f"├ <b>Премиум аккаунт:</b> {'Да' if is_premium else '⚠️ Нет'}\n"
            f"└ <b>Интервал обновления:</b> {userbot_interval} секунд\n\n"
            f"❗️ Статус 🔕 <b>приостанавливает</b> работу <b>юзербота</b>."
        )
        keyboard = [
            [
                status_button,
                InlineKeyboardButton(text="🗑 Удалить", callback_data="userbot_confirm_delete")
            ],
            [
                InlineKeyboardButton(text="📘 Инструкция", callback_data="show_userbot_help"),
                InlineKeyboardButton(text="⏳ Интервал", callback_data="userbot_interval"),
            ],
            [
                InlineKeyboardButton(text="☰ Меню", callback_data="userbot_main_menu")
            ]
        ]
    elif RESTART_REQUIRED.get(user_id):
        text = (
            "⚠️ <b>Вы запустили программу на платформе Windows или macOS</b>.\n"
            "🔁 Чтобы успешно <b>отключить</b> сессию или добавить нового Юзербота, пожалуйста, <b>перезапустите программу</b>."
        )
        keyboard = [
            [InlineKeyboardButton(text="📘 Инструкция", callback_data="show_userbot_help")],
            [InlineKeyboardButton(text="☰ Меню", callback_data="userbot_main_menu")]
        ]
    else:
        text = (
            "🚫 <b>Юзербот не подключён.</b>\n\n"
            "📋 <b>Подготовьте следующие данные:</b>\n\n"
            "🔸 <code>api_id</code>\n"
            "🔸 <code>api_hash</code>\n"
            "🔸 <code>Номер телефона</code>\n\n"
            "📎 Получить <b><a href=\"https://my.telegram.org\">API данные</a></b>\n"
            "📜 Прочитать <b><a href=\"https://core.telegram.org/api/terms\">условия использования</a></b>" 
        )
        keyboard = [
            [InlineKeyboardButton(text="➕ Подключить юзербот", callback_data="init_userbot")],
            [InlineKeyboardButton(text="📘 Инструкция", callback_data="show_userbot_help")],
            [InlineKeyboardButton(text="☰ Меню", callback_data="userbot_main_menu")]
        ]

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    try:
        if edit:
            await message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
        else:
            await message.answer(text, reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"⚠️ Ошибка при обновлении меню: {e}")


@wizard_router.callback_query(F.data == "userbot_interval")
async def on_userbot_interval(call: CallbackQuery):
    """
    Открывает меню выбора интервала обновления юзербота.
    """
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="30 секунд", callback_data="edit_userbot_interval_30"),
            InlineKeyboardButton(text="45 секунд", callback_data="edit_userbot_interval_45")
        ],
        [
            InlineKeyboardButton(text="60 секунд", callback_data="edit_userbot_interval_60"),
            InlineKeyboardButton(text="90 секунд", callback_data="edit_userbot_interval_90")
        ],
        [
            InlineKeyboardButton(text="⚙️ Юзербот", callback_data="userbot_menu_edit"),
            InlineKeyboardButton(text="☰ Меню", callback_data="userbot_main_menu")
        ]
    ])
    await call.message.edit_text(
        "⏳ Выберите интервал обновления списка подарков через юзербот:\n\n"
        "❗️ Рекомендуется использовать <b>45 секунд</b>.\n"
        "⚠️ Частые запросы могут привести к <b>блокировке или ограничению со стороны Telegram</b>.",
        reply_markup=kb
    )
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_userbot_interval_"))
async def edit_userbot_interval(call: CallbackQuery):
    """
    Обрабатывает изменение интервала обновления userbot.
    """
    interval_mapping = {
        "edit_userbot_interval_30": 30,
        "edit_userbot_interval_45": 45,
        "edit_userbot_interval_60": 60,
        "edit_userbot_interval_90": 90
    }

    interval = interval_mapping.get(call.data)
    if interval is None:
        await call.answer("🚫 Неверный интервал.", show_alert=True)
        return

    user_id = call.from_user.id
    config = await get_valid_config(user_id)
    config["USERBOT"]["UPDATE_INTERVAL"] = interval
    await save_config(config)

    await call.answer()
    await userbot_menu(call.message, user_id, edit=True)


@wizard_router.callback_query(F.data == "userbot_confirm_delete")
async def confirm_userbot_delete(call: CallbackQuery):
    """
    Запрашивает подтверждение удаления userbot-сессии у пользователя.
    """
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data="userbot_delete_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data="userbot_delete_no")
        ]
    ])
    await call.message.edit_text(
        "❗ Вы уверены, что хотите <b>удалить юзербот</b>?",
        reply_markup=kb
    )
    await call.answer()


@wizard_router.callback_query(F.data == "userbot_delete_no")
async def cancel_userbot_delete(call: CallbackQuery):
    """
    Отменяет процесс удаления userbot-сессии и возвращает в меню.
    """
    user_id = call.from_user.id
    await call.answer("Отменено.", show_alert=True)
    await userbot_menu(call.message, user_id, edit=True)


@wizard_router.callback_query(F.data == "userbot_delete_yes")
async def userbot_delete_handler(call: CallbackQuery):
    """
    Удаляет данные userbot-сессии из конфигурации пользователя.
    """
    user_id = call.from_user.id
    success = await delete_userbot_session(call, user_id)

    if success:
        await call.message.answer("✅ Юзербот удалён.")
        await userbot_menu(call.message, user_id, edit=False)
    else:
        await call.message.answer("🚫 Не удалось удалить юзербот. Возможно, он уже был удалена.")
        await userbot_menu(call.message, user_id, edit=False)

    await call.answer()


@wizard_router.callback_query(F.data == "userbot_enable")
async def userbot_enable_handler(call: CallbackQuery):
    """
    Включает userbot-сессию в конфигурации и обновляет меню.
    """
    user_id = call.from_user.id
    username = call.from_user.username
    bot_user = await call.bot.get_me()
    bot_username = bot_user.username
    config = await get_valid_config(user_id)
    config["USERBOT"]["ENABLED"] = True
    await save_config(config)

    await call.answer()

    text_message = (
        f"🔔 <b>Юзербот включён.</b>\n\n"
        f"┌🤖 <b>Бот:</b> @{bot_username}\n"
        f"├👤 <b>Пользователь:</b> @{username} (<code>{user_id}</code>)\n"
        f"└🕒 <b>Время:</b> {now_str()} (UTC)"
    )
    success_send_message = await userbot_send_self(user_id, text_message)

    if success_send_message:
        logger.info("Юзербот успешно включён.")
    else:
        logger.error("Юзербот успешно включён, но сообщение не удалось отправить.")

    await userbot_menu(call.message, user_id, edit=True)


@wizard_router.callback_query(F.data == "userbot_disable")
async def userbot_disable_handler(call: CallbackQuery):
    """
    Отключает userbot-сессию в конфигурации и обновляет меню.
    """
    user_id = call.from_user.id
    username = call.from_user.username
    bot_user = await call.bot.get_me()
    bot_username = bot_user.username
    config = await get_valid_config(user_id)
    config["USERBOT"]["ENABLED"] = False
    await save_config(config)

    await call.answer()

    text_message = (
        f"🔕 <b>Юзербот выключен.</b>\n\n"
        f"┌🤖 <b>Бот:</b> @{bot_username}\n"
        f"├👤 <b>Пользователь:</b> @{username} (<code>{user_id}</code>)\n"
        f"└🕒 <b>Время:</b> {now_str()} (UTC)"
    )
    success_send_message = await userbot_send_self(user_id, text_message)

    if success_send_message:
        logger.info("Юзербот успешно выключен.")
    else:
        logger.error("Юзербот успешно выключен, но сообщение не удалось отправить.")

    await userbot_menu(call.message, user_id, edit=True)


@wizard_router.callback_query(F.data == "init_userbot")
async def init_userbot_handler(call: CallbackQuery, state: FSMContext):
    """
    Запускает процесс подключения новой userbot-сессии (шаг ввода api_id).
    """
    await call.message.answer("📥 Введите <b>api_id</b>:\n\n/cancel — отмена")
    await state.set_state(ConfigWizard.userbot_api_id)
    await call.answer()


@wizard_router.message(ConfigWizard.userbot_api_id)
async def get_api_id(message: Message, state: FSMContext):
    """
    Обрабатывает ввод api_id от пользователя и переходит к следующему шагу.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    text = message.text.strip()

    if not text.isdigit() or not (10000 <= int(text) <= 9999999999):
        await message.answer("🚫 Неверный формат. Введите корректное число.\n\n/cancel — отмена")
        return
    
    value = int(text)
    await state.update_data(api_id=value)
    await message.answer("📥 Введите <b>api_hash</b>:\n\n/cancel — отмена")
    await state.set_state(ConfigWizard.userbot_api_hash)


@wizard_router.message(ConfigWizard.userbot_api_hash)
async def get_api_hash(message: Message, state: FSMContext):
    """
    Обрабатывает ввод api_hash и переходит к шагу ввода номера телефона.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    api_hash = message.text.strip()

    if not API_HASH_REGEX.fullmatch(api_hash):
        await message.answer("🚫 Неверный формат. Убедитесь, что api_hash скопирован полностью (32 символа).\n\n/cancel — отмена")
        return

    await state.update_data(api_hash=api_hash)
    await message.answer("📥 Введите номер телефона (в формате <code>+490123456789</code>):\n\n/cancel — отмена")
    await state.set_state(ConfigWizard.userbot_phone)


@wizard_router.message(ConfigWizard.userbot_phone)
async def get_phone(message: Message, state: FSMContext):
    """
    Сохраняет номер телефона и инициирует отправку кода подтверждения.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    raw_phone = message.text.strip()
    phone = raw_phone.replace(" ", "")

    if not PHONE_REGEX.match(phone):
        await message.answer("🚫 Неверный формат номера телефона.\nВведите в формате: <code>+490123456789</code>\n\n/cancel — отмена")
        return
    
    await state.update_data(phone=phone)

    success = await start_userbot(message, state)
    if not success:
        await userbot_menu(message, message.from_user.id, edit=False)
        await state.clear()
        return
    await state.set_state(ConfigWizard.userbot_code)
    await state.update_data(current_code="")
    await message.answer(text=f"📥 Введите полученный код:\n\n🔢 Код:\n\n⬅️ — удалить цифру\n🆗 — подтвердить код\n\n/cancel — отмена", reply_markup=create_digit_keyboard())


@wizard_router.callback_query(F.data.regexp(r"^code_\d$"), ConfigWizard.userbot_code)
async def on_code_digit(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает добавление цифры в код подтверждения через инлайн-клавиатуру.
    Обновляет состояние FSM и редактирует сообщение с клавиатурой.
    """
    digit = call.data.split('_')[1]
    data = await state.get_data()
    current_code = data.get("current_code", "") + digit
    await state.update_data(current_code=current_code)
    await call.answer()
    await call.bot.edit_message_text(
        f"📥 Введите полученный код:\n\n🔢 Код: <b>{current_code}</b>\n\n⬅️ — удалить цифру\n🆗 — подтвердить код\n\n/cancel — отмена",
        chat_id=call.from_user.id,
        message_id=call.message.message_id,
        reply_markup=create_digit_keyboard()
    )


@wizard_router.callback_query(F.data == "code_delete", ConfigWizard.userbot_code)
async def on_code_delete(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает удаление последней цифры из введённого кода подтверждения.
    Обновляет состояние FSM и редактирует сообщение с клавиатурой.
    """
    data = await state.get_data()
    current_code = data.get("current_code", "")[:-1]
    await state.update_data(current_code=current_code)
    await call.answer()
    await call.bot.edit_message_text(
        f"📥 Введите полученный код:\n\n🔢 Код: <b>{current_code}</b>\n\n⬅️ — удалить цифру\n🆗 — подтвердить код\n\n/cancel — отмена",
        chat_id=call.from_user.id,
        message_id=call.message.message_id,
        reply_markup=create_digit_keyboard()
    )


@wizard_router.callback_query(F.data == "code_enter", ConfigWizard.userbot_code)
async def on_code_enter(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает подтверждение кода через инлайн-клавиатуру.
    Проверяет длину кода (4-6 символов) перед обработкой.
    """
    data = await state.get_data()
    current_code = data.get("current_code", "")

    if not (4 <= len(current_code) <= 6):
        await call.answer("🚫 Код должен быть от 4 до 6 символов. Попробуйте ещё раз.", show_alert=True)
        return
    
    await call.bot.edit_message_text(
        f"🔢 Введённый код: <b>{current_code}</b>",
        chat_id=call.from_user.id,
        message_id=call.message.message_id
    )

    await state.update_data(code=current_code)
    success, need_password, retry = await continue_userbot_signin(call, state)
    if retry:
        await state.set_state(ConfigWizard.userbot_code)
        await state.update_data(current_code="")
        await call.message.answer(text=f"📥 Введите полученный код:\n\n🔢 Код:\n\n⬅️ — удалить цифру\n🆗 — подтвердить код\n\n/cancel — отмена", reply_markup=create_digit_keyboard())
        return
    if not success:
        await call.message.answer("🚫 Ошибка кода. Подключение юзербота прервано.")
        await userbot_menu(call.message, call.from_user.id, edit=False)
        await state.clear()
        await call.answer()
        return
    if need_password:
        await call.message.answer("📥 Введите пароль:\n\n/cancel — отмена")
        await state.set_state(ConfigWizard.userbot_password)
    else:
        user_id = call.from_user.id
        username = call.from_user.username
        bot_user = await call.bot.get_me()
        bot_username = bot_user.username

        config = await get_valid_config(user_id)
        config_id = config["USERBOT"].get("CONFIG_ID")
        device_model = DEVICE_MODELS[config_id]
        system_version = SYSTEM_VERSIONS[config_id]
        app_version = APP_VERSIONS[config_id]
        text_success_message = (
            f"✅ <b>Userbot-сессия успешно авторизована через Telegram-бота.</b>\n\n"
            f"┌🤖 <b>Бот:</b> @{bot_username}\n"
            f"├👤 <b>Пользователь:</b> @{username} (<code>{user_id}</code>)\n"
            f"├📱 <b>Модель устройства:</b> {device_model}\n"
            f"├🖥️ <b>Версия системы:</b> {system_version}\n"
            f"└📱 <b>Версия приложения:</b> {app_version}\n"
        )

        success_send_message = await userbot_send_self(user_id, text_success_message)

        if success_send_message:
            await call.message.answer("✅ Юзербот успешно подключён.")
        else:
            await call.message.answer("✅ Юзербот успешно подключён.\n🚫 Ошибка при отправке подтверждения.")

        await userbot_menu(call.message, call.from_user.id, edit=False)
        await state.clear()
    await call.answer()


@wizard_router.message(ConfigWizard.userbot_password)
async def get_password(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пароля от Telegram-аккаунта и завершает авторизацию userbot'а.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    await state.update_data(password=message.text.strip())
    success, retry = await finish_userbot_signin(message, state)
    if retry:
        return
    if success:
        user_id = message.from_user.id
        username = message.from_user.username
        bot_user = await message.bot.get_me()
        bot_username = bot_user.username
        config = await get_valid_config(user_id)
        config_id = config["USERBOT"].get("CONFIG_ID")
        device_model = DEVICE_MODELS[config_id]
        system_version = SYSTEM_VERSIONS[config_id]
        app_version = APP_VERSIONS[config_id]
        text_success_message = (
            f"✅ <b>Userbot-сессия успешно авторизована через Telegram-бота.</b>\n\n"
            f"┌🤖 <b>Бот:</b> @{bot_username}\n"
            f"├👤 <b>Пользователь:</b> @{username} (<code>{user_id}</code>)\n"
            f"├📱 <b>Модель устройства:</b> {device_model}\n"
            f"├🖥️ <b>Версия системы:</b> {system_version}\n"
            f"└📱 <b>Версия приложения:</b> {app_version}\n"
        )

        success_send_message = await userbot_send_self(user_id, text_success_message)

        if success_send_message:
            await message.answer("✅ Юзербот успешно подключён.")
        else:
            await message.answer("✅ Юзербот успешно подключён.\n🚫 Ошибка при отправке подтверждения.")
    else:
        await message.answer("🚫 Неверный пароль. Подключение юзербота прервано.")

    await userbot_menu(message, message.from_user.id, edit=False)
    await state.clear()


@wizard_router.callback_query(F.data == "userbot_main_menu")
async def userbot_main_menu_callback(call: CallbackQuery, state: FSMContext):
    """
    Показывает главное меню по нажатию кнопки "Меню".
    Очищает все состояния FSM для пользователя.
    """
    await state.clear()
    await call.answer()
    await safe_edit_text(call.message, "✅ Настройка юзербота завершена.", reply_markup=None)
    await refresh_balance(call.bot)
    await update_menu(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        message_id=call.message.message_id
    )


async def profiles_menu(message: Message, user_id: int) -> None:
    """
    Показывает пользователю главное меню управления профилями.
    Отображает список всех созданных профилей и предоставляет кнопки для их редактирования, удаления или добавления нового профиля.
    """
    config = await get_valid_config(user_id)
    profiles = config.get("PROFILES", [])

    # Формируем клавиатуру профилей
    keyboard = []
    for idx, profile in enumerate(profiles):
        profile_name = f'Профиль {idx + 1}' if  not profile['NAME'] else profile['NAME']
        btns = [
            InlineKeyboardButton(
                text=f"✏️ {profile_name}", callback_data=f"profile_edit_{idx}"
            ),
            InlineKeyboardButton(
                text="🗑 Удалить", callback_data=f"profile_delete_{idx}"
            ),
        ]
        keyboard.append(btns)
    # Кнопка добавления (максимум 4 профиля)
    if len(profiles) < MAX_PROFILES:
        keyboard.append([InlineKeyboardButton(text="➕ Добавить", callback_data="profile_add")])
    # Кнопка назад
    keyboard.append([InlineKeyboardButton(text="☰ Меню", callback_data="profiles_main_menu")])

    profiles = config.get("PROFILES", [])

    lines = []
    for idx, profile in enumerate(profiles, 1):
        target_display = get_target_display(profile, user_id)
        profile_name = f'Профиль {idx}' if  not profile['NAME'] else profile['NAME']
        sender = '<code>Бот</code>' if profile['SENDER'] == 'bot' else '<code>Юзербот</code>'
        if idx == 1 and len(profiles) == 1: line = (f"🏷️ <b>{profile_name} {sender}</b> → {target_display}")
        elif idx == 1: line = (f"┌🏷️ <b>{profile_name} {sender}</b> → {target_display}")
        elif len(profiles) == idx: line = (f"└🏷️ <b>{profile_name} {sender}</b> → {target_display}")
        else: line = (f"├🏷️ <b>{profile_name} {sender}</b> → {target_display}")
        lines.append(line)
    text_profiles = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.answer(f"📝 <b>Управление профилями (максимум 4):</b>\n\n"
                         f"{text_profiles}\n\n"
                         "👉 <b>Нажмите</b> ✏️ чтобы изменить профиль.\n", 
                         reply_markup=kb)


@wizard_router.callback_query(F.data == "profiles_menu")
async def on_profiles_menu(call: CallbackQuery):
    """
    Обрабатывает нажатие на кнопку "Профили" или переход к списку профилей.
    Открывает меню со всеми профилями пользователя и возможностью их редактирования или удаления.
    """
    await profiles_menu(call.message, call.from_user.id)
    await call.answer()


def profile_text(profile: dict, idx: int, user_id: int) -> str:
    """
    Формирует текстовое описание параметров профиля по его данным.
    Включает цены, лимиты, supply, получателя и другую основную информацию по выбранному профилю.
    Используется для вывода информации при редактировании профиля.
    """
    target_display = get_target_display(profile, user_id)
    profile_name = f'Профиль {idx + 1}' if  not profile['NAME'] else profile['NAME']
    sender = '<code>Бот</code>' if profile['SENDER'] == 'bot' else '<code>Юзербот</code>'
    return (f"✏️ <b>Изменение {profile_name}</b>:\n\n"
            f"┌💰 <b>Цена</b>: {profile.get('MIN_PRICE'):,} – {profile.get('MAX_PRICE'):,} ★\n"
            f"├📦 <b>Саплай</b>: {profile.get('MIN_SUPPLY'):,} – {profile.get('MAX_SUPPLY'):,}\n"
            f"├🎁 <b>Куплено</b>: {profile.get('BOUGHT'):,} / {profile.get('COUNT'):,}\n"
            f"├⭐️ <b>Лимит</b>: {profile.get('SPENT'):,} / {profile.get('LIMIT'):,} ★\n"
            f"├👤 <b>Получатель</b>: {target_display}\n"
            f"└📤 <b>Отправитель</b>: {sender}")


def profile_edit_keyboard(idx: int) -> InlineKeyboardMarkup:
    """
    Создаёт инлайн-клавиатуру для быстрого редактирования параметров выбранного профиля.
    Каждая кнопка отвечает за редактирование отдельного поля (цены, supply, лимита и т.д.).
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 Цена", callback_data=f"edit_profile_price_{idx}"),
                InlineKeyboardButton(text="📦 Саплай", callback_data=f"edit_profile_supply_{idx}"),
            ],
            [
                InlineKeyboardButton(text="🎁 Количество", callback_data=f"edit_profile_count_{idx}"),
                InlineKeyboardButton(text="⭐️ Лимит", callback_data=f"edit_profile_limit_{idx}")
            ],
            [
                InlineKeyboardButton(text="👤 Получатель", callback_data=f"edit_profile_target_{idx}"),
                InlineKeyboardButton(text="📤 Отправитель", callback_data=f"edit_profile_sender_{idx}")
            ],
            [
                InlineKeyboardButton(text="🏷️ Название", callback_data=f"edit_profile_name_{idx}"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"edit_profiles_menu_{idx}")
            ],
            [
                InlineKeyboardButton(text="☰ Меню", callback_data="profiles_main_menu")
            ]
        ]
    )


@wizard_router.callback_query(lambda c: c.data.startswith("profile_edit_"))
async def on_profile_edit(call: CallbackQuery, state: FSMContext):
    """
    Открывает экран подробного редактирования конкретного профиля.
    Показывает все параметры профиля и инлайн-кнопки для выбора нужного параметра для изменения.
    """
    idx = int(call.data.split("_")[-1])
    config = await get_valid_config(call.from_user.id)
    profile = config["PROFILES"][idx]
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    await call.message.edit_text(
        profile_text(profile, idx, call.from_user.id),
        reply_markup=profile_edit_keyboard(idx)
    )
    await call.answer()


@wizard_router.message(ConfigWizard.edit_profile_name)
async def on_profile_name_entered(message: Message, state: FSMContext):
    """
    Обработка ввода нового имени профиля.

    Аргументы:
    - message: Объект сообщения, содержащий введённое имя.
    - state: Контекст состояния FSM.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    name = message.text.strip()
    if not is_valid_profile_name(name):
        await message.answer("🚫 Имя должно содержать только буквы (русские и латинские) и цифры, "
                             "и быть не длиннее 12 символов. Попробуйте ещё раз.\n\n"
                             "/cancel — отмена")
        return

    data = await state.get_data()
    idx = data.get("profile_index")
    if idx is None:
        await message.answer("Ошибка: не выбран профиль для переименования.")
        await state.clear()
        return

    config = await get_valid_config(message.from_user.id)
    profiles = config.get("PROFILES", [])
    if idx < 0 or idx >= len(profiles):
        await message.answer("Ошибка: профиль не найден.")
        await state.clear()
        return

    profiles[idx]["NAME"] = name
    await save_config(config)
    await message.answer(f"✅ Имя профиля успешно изменено на: <b>{name}</b>")

    # Вернуться к меню профилей (вызывайте свою функцию профилей)
    await profiles_menu(message, message.from_user.id)
    await state.clear()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_price_"))
async def edit_profile_min_price(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку изменения минимальной цены в профиле.
    Переводит пользователя в состояние ввода новой минимальной цены.
    """
    idx = int(call.data.split("_")[-1])
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    config = await get_valid_config(call.from_user.id)
    profiles = config.get("PROFILES", [])
    profile = profiles[idx]
    profile_name = f'профиля {idx+1}' if  not profile['NAME'] else profile['NAME']
    await call.message.answer(f"✏️ <b>Редактирование {profile_name}:</b>\n\n"
                              "💰 Минимальная цена подарка, например: <code>5000</code>\n\n"
                              "/cancel — отмена")
    await state.set_state(ConfigWizard.edit_min_price)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_supply_"))
async def edit_profile_min_supply(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку изменения минимального supply для профиля.
    Переводит пользователя в состояние ввода нового минимального значения supply.
    """
    idx = int(call.data.split("_")[-1])
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    config = await get_valid_config(call.from_user.id)
    profiles = config.get("PROFILES", [])
    profile = profiles[idx]
    profile_name = f'профиля {idx+1}' if  not profile['NAME'] else profile['NAME']
    await call.message.answer(f"✏️ <b>Редактирование {profile_name}:</b>\n\n"
                              "📦 Минимальный саплай подарка, например: <code>1000</code>\n\n"
                              "/cancel — отмена")
    await state.set_state(ConfigWizard.edit_min_supply)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_limit_"))
async def edit_profile_limit(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку изменения лимита по звёздам (максимальной суммы расходов) для профиля.
    Переводит пользователя в состояние ввода нового лимита.
    """
    idx = int(call.data.split("_")[-1])
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    config = await get_valid_config(call.from_user.id)
    profiles = config.get("PROFILES", [])
    profile = profiles[idx]
    profile_name = f'профиля {idx+1}' if  not profile['NAME'] else profile['NAME']
    await call.message.answer(f"✏️ <b>Редактирование {profile_name}:</b>\n\n"
                              "⭐️ Введите лимит звёзд для этого профиля (например: <code>10000</code>)\n\n"
                              "/cancel — отмена")
    await state.set_state(ConfigWizard.edit_limit)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_count_"))
async def edit_profile_count(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку изменения количества подарков в профиле.
    Переводит пользователя в состояние ввода нового количества.
    """
    idx = int(call.data.split("_")[-1])
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    config = await get_valid_config(call.from_user.id)
    profiles = config.get("PROFILES", [])
    profile = profiles[idx]
    profile_name = f'профиля {idx+1}' if  not profile['NAME'] else profile['NAME']
    await call.message.answer(f"✏️ <b>Редактирование {profile_name}:</b>\n\n"
                              "🎁 Максимальное количество подарков, например: <code>5</code>\n\n"
                              "/cancel — отмена")
    await state.set_state(ConfigWizard.edit_count)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_target_"))
async def edit_profile_target(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие на кнопку изменения получателя подарков (user_id или @username).
    Переводит пользователя в состояние ввода нового получателя.
    """
    idx = int(call.data.split("_")[-1])
    await state.update_data(profile_index=idx)
    await state.update_data(message_id=call.message.message_id)
    config = await get_valid_config(call.from_user.id)
    profiles = config.get("PROFILES", [])
    profile = profiles[idx]
    profile_name = f'профиля {idx+1}' if  not profile['NAME'] else profile['NAME']
    message_text = (f"✏️ <b>Редактирование {profile_name}:</b>\n\n"
                    "📥 Введите <b>получателя</b> подарка:\n\n"
                    "🤖 Если <b>отправитель</b> <code>Бот</code> введите:\n"
                    f"➤ <b>ID пользователя</b> (например ваш: <code>{call.from_user.id}</code>)\n"
                    "➤ <b>username канала</b> (например: <code>@pepeksey</code>)\n\n"
                    "👤 Если <b>отправитель</b> <code>Юзербот</code> введите:\n"
                    "➤ <b>username пользователя</b> (например: <code>@leozizu</code>)\n"
                    "➤ <b>username канала</b> (например: <code>@pepeksey</code>)\n\n"
                    "🔎 <b>Узнать ID пользователя</b> можно тут: @userinfobot\n\n"
                    "⚠️ Чтобы аккаунт <code>Юзербота</code> отправил подарок на другой аккаунт, между аккаунтами должна быть переписка.\n\n"
                    "/cancel — отмена")
    await call.message.answer(message_text)
    await state.set_state(ConfigWizard.edit_user_id)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_name_"))
async def edit_profile_name(call: CallbackQuery, state: FSMContext):
    """
    Кнопка "Переименовать профиль". Сохраняет индекс и ждет новое имя.
    """
    idx = int(call.data.split("_")[-1])
    config = await get_valid_config(call.from_user.id)
    profiles = config.get("PROFILES", [])

    if idx >= len(profiles):
        await call.answer("Профиль не найден.", show_alert=True)
        return
    
    profile = profiles[idx]

    await state.update_data(profile_index=idx)
    profile_name = f'профиля {idx+1}' if  not profile['NAME'] else profile['NAME']
    await call.message.answer(f"✏️ Введите новое имя для профиля <b>{profile_name}</b>: (до 12 символов)\n\n"
                              "/cancel — отмена")
    await state.set_state(ConfigWizard.edit_profile_name)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profile_sender_"))
async def edit_profile_sender(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор отправителя подарков для профиля.
    Переводит пользователя в состояние выбора отправителя.
    """
    idx = int(call.data.removeprefix("edit_profile_sender_"))
    config = await get_valid_config(call.from_user.id)
    profiles = config.get("PROFILES", [])

    if idx >= len(profiles):
        await call.answer("Профиль не найден.", show_alert=True)
        return

    profile = profiles[idx]

    # Сохраняем профиль в FSM (будем его редактировать)
    await state.set_state(ConfigWizard.edit_gift_sender)
    await state.update_data(profile_data=profile, profile_index=idx)

    profile_name = f'профиля {idx+1}' if  not profile['NAME'] else profile['NAME']
    await call.message.edit_text(f"✏️ <b>Редактирование {profile_name}:</b>\n\n"
                                 "📤 Выберите <b>отправителя</b> подарков:\n\n"
                                 "🤖 <code>Бот</code> - покупки с баланса бота\n"
                                 "👤 <code>Юзербот</code> - покупки с баланса юзербота\n\n"
                                 "❗️ Если отправитель <code>Юзербот</code>, убедитесь, что он <b>включён</b> 🔔\n\n"
                                 "/cancel — отмена",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Бот", callback_data="choose_sender_bot"),
                InlineKeyboardButton(text="👤 Юзербот", callback_data="choose_sender_userbot")
            ]
        ])
    )
    await call.answer()


@wizard_router.message(ConfigWizard.gift_sender)
async def handle_gift_sender_input(message: Message, state: FSMContext):
    """
    Обрабатывает ввод на шаге выбора отправителя. Позволяет отменить командой /cancel.
    """
    if await try_cancel(message, state):
        return

    await message.answer("❗ Пожалуйста, выберите отправителя с помощью кнопок.\n\n"
                         "/cancel — отмена")


@wizard_router.message(ConfigWizard.edit_gift_sender)
async def handle_gift_sender_input(message: Message, state: FSMContext):
    """
    Обрабатывает ввод на шаге выбора отправителя. Позволяет отменить командой /cancel.
    """
    if await try_cancel(message, state):
        return

    await message.answer("❗ Пожалуйста, выберите отправителя с помощью кнопок.\n\n"
                         "/cancel — отмена")


@wizard_router.callback_query(lambda c: c.data.startswith("edit_profiles_menu_"))
async def edit_profiles_menu(call: CallbackQuery):
    """
    Обрабатывает возврат из режима редактирования профиля в основное меню профилей.
    Открывает пользователю общий список всех профилей.
    """
    idx = int(call.data.split("_")[-1])
    config = await get_valid_config(call.from_user.id)
    profiles = config.get("PROFILES", [])
    profile = profiles[idx]
    profile_name = f'профиля {idx+1}' if  not profile['NAME'] else profile['NAME']
    await safe_edit_text(call.message, f"✅ Редактирование <b>{profile_name}</b> завершено.", reply_markup=None)
    await profiles_menu(call.message, call.from_user.id)
    await call.answer()


@wizard_router.message(ConfigWizard.edit_min_price)
async def step_edit_min_price(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового значения минимальной цены для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    data = await state.get_data()
    idx = data["profile_index"]
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_PRICE=value)
        config = await get_valid_config(message.from_user.id)
        profiles = config.get("PROFILES", [])
        profile = profiles[idx]
        profile_name = f'профиля {idx+1}' if  not profile['NAME'] else profile['NAME']
        await message.answer(f"✏️ <b>Редактирование {profile_name}:</b>\n\n"
                             "💰 Максимальная цена подарка, например: <code>10000</code>\n\n"
                             "/cancel — отмена")
        await state.set_state(ConfigWizard.edit_max_price)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.message(ConfigWizard.edit_max_price)
async def step_edit_max_price(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового значения максимальной цены для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    data = await state.get_data()
    idx = data["profile_index"]
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_price = data.get("MIN_PRICE")
        if min_price and value < min_price:
            await message.answer("🚫 Максимальная цена не может быть меньше минимальной. Попробуйте ещё раз.\n\n/cancel — отмена")
            return

        config = await get_valid_config(message.from_user.id)
        config["PROFILES"][idx]["MIN_PRICE"] = data["MIN_PRICE"]
        config["PROFILES"][idx]["MAX_PRICE"] = value
        await save_config(config)

        try:
            await message.bot.delete_message(message.chat.id, data["message_id"])
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

        await message.answer(
            profile_text(config["PROFILES"][idx], idx, message.from_user.id),
            reply_markup=profile_edit_keyboard(idx)
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.message(ConfigWizard.edit_min_supply)
async def step_edit_min_supply(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового значения минимального supply для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    data = await state.get_data()
    idx = data["profile_index"]
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_SUPPLY=value)
        config = await get_valid_config(message.from_user.id)
        profiles = config.get("PROFILES", [])
        profile = profiles[idx]
        profile_name = f'профиля {idx+1}' if  not profile['NAME'] else profile['NAME']
        await message.answer(f"✏️ <b>Редактирование {profile_name}:</b>\n\n"
                             "📦 Максимальный саплай подарка, например: <code>10000</code>\n\n"
                             "/cancel — отмена")
        await state.set_state(ConfigWizard.edit_max_supply)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.message(ConfigWizard.edit_max_supply)
async def step_edit_max_supply(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового значения максимального саплая для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    data = await state.get_data()
    idx = data["profile_index"]
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_supply = data.get("MIN_SUPPLY")
        if min_supply and value < min_supply:
            await message.answer("🚫 Максимальный саплай не может быть меньше минимального. Попробуйте ещё раз.\n\n/cancel — отмена")
            return
        
        config = await get_valid_config(message.from_user.id)
        config["PROFILES"][idx]["MIN_SUPPLY"] = data["MIN_SUPPLY"]
        config["PROFILES"][idx]["MAX_SUPPLY"] = value
        await save_config(config)

        try:
            await message.bot.delete_message(message.chat.id, data["message_id"])
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

        await message.answer(
            profile_text(config["PROFILES"][idx], idx, message.from_user.id),
            reply_markup=profile_edit_keyboard(idx)
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.message(ConfigWizard.edit_limit)
async def step_edit_limit(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового значения лимита (максимальной суммы расходов) для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return

    data = await state.get_data()
    idx = data["profile_index"]

    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        
        config = await get_valid_config(message.from_user.id)
        config["PROFILES"][idx]["LIMIT"] = value
        await save_config(config)

        try:
            await message.bot.delete_message(message.chat.id, data["message_id"])
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

        await message.answer(
            profile_text(config["PROFILES"][idx], idx, message.from_user.id),
            reply_markup=profile_edit_keyboard(idx)
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.message(ConfigWizard.edit_count)
async def step_edit_count(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового количества подарков для профиля.
    Проверяет валидность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    data = await state.get_data()
    idx = data["profile_index"]

    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        
        config = await get_valid_config(message.from_user.id)
        config["PROFILES"][idx]["COUNT"] = value
        await save_config(config)

        try:
            await message.bot.delete_message(message.chat.id, data["message_id"])
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение: {e}")

        await message.answer(
            profile_text(config["PROFILES"][idx], idx, message.from_user.id),
            reply_markup=profile_edit_keyboard(idx)
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.message(ConfigWizard.edit_user_id)
async def step_edit_user_id(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем нового получателя (user_id или @username) для профиля.
    Проверяет корректность, сохраняет и возвращает пользователя в меню профиля.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    data = await state.get_data()
    idx = data["profile_index"]

    user_input = message.text.strip()
    if user_input.startswith("@"):
        chat_type = await get_chat_type(bot=message.bot, username=user_input)
        if chat_type == "channel":
            target_chat = user_input
            target_user = None
            target_type = "channel"
        elif chat_type == "unknown":
            target_chat = user_input
            target_user = None
            target_type = "username"
        else:
            await message.answer("🚫 Вы указали неправильный <b>username канала</b>. Попробуйте ещё раз.\n\n/cancel — отмена")
            return
    elif user_input.isdigit():
        target_chat = None
        target_user = int(user_input)
        target_type = "user_id"
    else:
        await message.answer("🚫 Введите ID или @username канала. Попробуйте ещё раз.\n\n/cancel — отмена")
        return
    
    config = await get_valid_config(message.from_user.id)
    config["PROFILES"][idx]["TARGET_USER_ID"] = target_user
    config["PROFILES"][idx]["TARGET_CHAT_ID"] = target_chat
    config["PROFILES"][idx]["TARGET_TYPE"] = target_type
    await save_config(config)

    try:
        await message.bot.delete_message(message.chat.id, data["message_id"])
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    await message.answer(
            profile_text(config["PROFILES"][idx], idx, message.from_user.id),
            reply_markup=profile_edit_keyboard(idx)
        )
    await state.clear()


@wizard_router.callback_query(F.data == "choose_sender_bot")
async def choose_sender_bot(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор отправителя «Бот» при оформлении подарка.
    """
    await save_sender_and_finish(call, state, sender="bot")

@wizard_router.callback_query(F.data == "choose_sender_userbot")
async def choose_sender_userbot(call: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор отправителя «Юзербот» при оформлении подарка.
    """
    await save_sender_and_finish(call, state, sender="userbot")

async def save_sender_and_finish(call: CallbackQuery, state: FSMContext, sender: str) -> None:
    """
    Сохраняет выбранного отправителя (бот или юзербот) в состояние FSM 
    и завершает процесс, возвращая пользователя в главное меню.
    """
    data = await state.get_data()
    profile_data = data.get("profile_data")
    idx = data.get("profile_index")  # None — новый, число — редактирование

    if not profile_data:
        await call.message.answer("❌ Ошибка: профиль не найден.")
        await state.clear()
        return
    
    profile_data["SENDER"] = sender

    config = await get_valid_config(call.from_user.id)

    if idx is None:
        await add_profile(config, profile_data)
        msg = "✅ <b>Новый профиль</b> создан."
        await call.message.edit_text(msg)
        await profiles_menu(call.message, call.from_user.id)
    else:
        await update_profile(config, idx, profile_data)
        msg = f"✅ <b>Профиль {idx + 1}</b> обновлён."
        await call.message.edit_text(msg)
        await call.message.answer(
            profile_text(config["PROFILES"][idx], idx, call.from_user.id),
            reply_markup=profile_edit_keyboard(idx)
        )

    await state.clear()
    await call.answer()

@wizard_router.callback_query(F.data == "profile_add")
async def on_profile_add(call: CallbackQuery, state: FSMContext):
    """
    Запускает мастер пошагового создания нового профиля подарков.
    Переводит пользователя к первому этапу ввода параметров нового профиля.
    """
    await state.update_data(profile_index=None)
    await call.message.answer("➕ Добавление <b>нового профиля</b>.\n\n"
                              "💰 Минимальная цена подарка, например: <code>5000</code>\n\n"
                              "/cancel — отмена", reply_markup=None)
    await state.set_state(ConfigWizard.min_price)
    await call.answer()


@wizard_router.message(ConfigWizard.user_id)
async def step_user_id(message: Message, state: FSMContext):
    """
    Обрабатывает ввод адреса получателя (user ID или username) и сохраняет профиль.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return

    user_input = message.text.strip()
    if user_input.startswith("@"):
        chat_type = await get_chat_type(bot=message.bot, username=user_input)
        if chat_type == "channel":
            target_chat = user_input
            target_user = None
            target_type = "channel"
        elif chat_type == "unknown":
            target_chat = user_input
            target_user = None
            target_type = "username"
        else:
            await message.answer("🚫 Вы указали неправильный <b>username канала</b>. Попробуйте ещё раз.\n\n/cancel — отмена")
            return
    elif user_input.isdigit():
        target_chat = None
        target_user = int(user_input)
        target_type = "user_id"
    else:
        await message.answer("🚫 Введите ID или @username канала. Попробуйте ещё раз.\n\n/cancel — отмена")
        return

    data = await state.get_data()
    profile_data = {
        "MIN_PRICE": data["MIN_PRICE"],
        "MAX_PRICE": data["MAX_PRICE"],
        "MIN_SUPPLY": data["MIN_SUPPLY"],
        "MAX_SUPPLY": data["MAX_SUPPLY"],
        "LIMIT": data["LIMIT"],
        "COUNT": data["COUNT"],
        "TARGET_USER_ID": target_user,
        "TARGET_CHAT_ID": target_chat,
        "TARGET_TYPE": target_type,
        "BOUGHT": 0,
        "SPENT": 0,
        "DONE": False,
    }

    await state.update_data(profile_data=profile_data)

    # Переход к шагу выбора отправителя
    await message.answer("📤 Выберите <b>отправителя</b> подарков:\n\n"
                         "🤖 <code>Бот</code> - покупки с баланса бота\n"
                         "👤 <code>Юзербот</code> - покупки с баланса юзербота\n\n"
                         "/cancel — отмена",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Бот", callback_data="choose_sender_bot"),
                InlineKeyboardButton(text="👤 Юзербот", callback_data="choose_sender_userbot")
            ]
        ])
    )
    await state.set_state(ConfigWizard.gift_sender)


@wizard_router.callback_query(F.data == "profiles_main_menu")
async def profiles_main_menu_callback(call: CallbackQuery, state: FSMContext):
    """
    Показывает главное меню по нажатию кнопки "Меню".
    Очищает все состояния FSM для пользователя.
    """
    await state.clear()
    await call.answer()
    await safe_edit_text(call.message, "✅ Редактирование профилей завершено.", reply_markup=None)
    await refresh_balance(call.bot)
    await update_menu(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        message_id=call.message.message_id
    )


@wizard_router.callback_query(lambda c: c.data.startswith("profile_delete_"))
async def on_profile_delete_confirm(call: CallbackQuery, state: FSMContext):
    """
    Запрашивает подтверждение удаления профиля.
    """
    idx = int(call.data.split("_")[-1])
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_delete_{idx}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_delete_{idx}"),
            ]
        ]
    )
    config = await get_valid_config(call.from_user.id)
    profiles = config.get("PROFILES", [])
    profile = profiles[idx]
    target_display = get_target_display(profile, call.from_user.id)
    profile_name = f'Профиль {idx + 1}' if  not profile['NAME'] else profile['NAME']
    sender = '<code>Бот</code>' if profile['SENDER'] == 'bot' else '<code>Юзербот</code>'
    message = (f"┌🏷️ <b>{profile_name}</b> (куплено {profile.get('BOUGHT'):,} из {profile.get('COUNT'):,})\n"
            f"├💰 <b>Цена</b>: {profile.get('MIN_PRICE'):,} – {profile.get('MAX_PRICE'):,} ★\n"
            f"├📦 <b>Саплай</b>: {profile.get('MIN_SUPPLY'):,} – {profile.get('MAX_SUPPLY'):,}\n"
            f"├⭐️ <b>Лимит</b>: {profile.get('SPENT'):,} / {profile.get('LIMIT'):,} ★\n"
            f"├👤 <b>Получатель</b>: {target_display}\n"
            f"└📤 <b>Отправитель</b>: {sender}")
    await call.message.edit_text(
        f"⚠️ Вы уверены, что хотите <b>удалить</b> профиль?\n\n{message}",
        reply_markup=kb
    )
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("confirm_delete_"))
async def on_profile_delete_final(call: CallbackQuery):
    """
    Окончательно удаляет профиль после подтверждения.
    """
    idx = int(call.data.split("_")[-1])
    config = await get_valid_config(call.from_user.id)
    default_added = ("\n➕ <b>Добавлен</b> стандартный профиль.\n"
                     "🚦 Статус изменён на 🔴 (неактивен)." if len(config["PROFILES"]) == 1 else "")
    if len(config["PROFILES"]) == 1:
        config["ACTIVE"] = False
        await save_config(config)
    await remove_profile(config, idx, call.from_user.id)
    await call.message.edit_text(f"✅ <b>Профиль {idx + 1}</b> удалён.{default_added}", reply_markup=None)
    await profiles_menu(call.message, call.from_user.id)
    await call.answer()


@wizard_router.callback_query(lambda c: c.data.startswith("cancel_delete_"))
async def on_profile_delete_cancel(call: CallbackQuery):
    """
    Отмена удаления профиля.
    """
    idx = int(call.data.split("_")[-1])
    await call.message.edit_text(f"🚫 Удаление <b>профиля {idx + 1}</b> отменено.", reply_markup=None)
    await profiles_menu(call.message, call.from_user.id)
    await call.answer()


async def safe_edit_text(message: Message, text: str, reply_markup: InlineKeyboardMarkup = None) -> bool:
    """
    Безопасно редактирует текст сообщения, игнорируя ошибки "нельзя редактировать" и "сообщение не найдено".
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        logger.error(f"Ошибка редактирования сообщения: {e}")
        if "message can't be edited" in str(e) or "message to edit not found" in str(e):
            # Просто игнорируем — сообщение устарело или удалено
            return False
        else:
            raise


@wizard_router.callback_query(F.data == "edit_config")
async def edit_config_handler(call: CallbackQuery, state: FSMContext):
    """
    Запуск мастера редактирования конфигурации.
    """
    await call.message.answer("💰 Минимальная цена подарка, например: <code>5000</code>\n\n/cancel — отмена")
    await state.set_state(ConfigWizard.min_price)
    await call.answer()


@wizard_router.message(ConfigWizard.min_price)
async def step_min_price(message: Message, state: FSMContext):
    """
    Обработка ввода минимальной цены подарка.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_PRICE=value)
        await message.answer("💰 Максимальная цена подарка, например: <code>10000</code>\n\n/cancel — отмена")
        await state.set_state(ConfigWizard.max_price)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.message(ConfigWizard.max_price)
async def step_max_price(message: Message, state: FSMContext):
    """
    Обработка ввода максимальной цены подарка и проверка корректности диапазона.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_price = data.get("MIN_PRICE")
        if min_price and value < min_price:
            await message.answer("🚫 Максимальная цена не может быть меньше минимальной. Попробуйте ещё раз.\n\n/cancel — отмена")
            return

        await state.update_data(MAX_PRICE=value)
        await message.answer("📦 Минимальный саплай подарка, например: <code>1000</code>\n\n/cancel — отмена")
        await state.set_state(ConfigWizard.min_supply)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.message(ConfigWizard.min_supply)
async def step_min_supply(message: Message, state: FSMContext):
    """
    Обработка ввода минимального саплая для подарка.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(MIN_SUPPLY=value)
        await message.answer("📦 Максимальный саплай подарка, например: <code>10000</code>\n\n/cancel — отмена")
        await state.set_state(ConfigWizard.max_supply)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.message(ConfigWizard.max_supply)
async def step_max_supply(message: Message, state: FSMContext):
    """
    Обработка ввода максимального саплая для подарка, проверка диапазона.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError

        data = await state.get_data()
        min_supply = data.get("MIN_SUPPLY")
        if min_supply and value < min_supply:
            await message.answer("🚫 Максимальный саплай не может быть меньше минимального. Попробуйте ещё раз.\n\n/cancel — отмена")
            return

        await state.update_data(MAX_SUPPLY=value)
        await message.answer("🎁 Максимальное количество подарков, например: <code>5</code>\n\n/cancel — отмена")
        await state.set_state(ConfigWizard.count)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.message(ConfigWizard.count)
async def step_count(message: Message, state: FSMContext):
    """
    Обработка ввода количества подарков.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(COUNT=value)
        await message.answer(
            "⭐️ Введите лимит звёзд для этого профиля (например: <code>10000</code>)\n\n"
            "/cancel — отмена"
        )
        await state.set_state(ConfigWizard.limit)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.message(ConfigWizard.limit)
async def step_limit(message: Message, state: FSMContext):
    """
    Обработка ввода лимита звёзд на ордер.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return

    try:
        value = int(message.text)
        if value <= 0:
            raise ValueError
        await state.update_data(LIMIT=value)
        message_text = ("📥 Введите <b>получателя</b> подарка:\n\n"
                        "🤖 Если <b>отправитель</b> <code>Бот</code> введите:\n"
                        f"➤ <b>ID пользователя</b> (например ваш: <code>{message.from_user.id}</code>)\n"
                        "➤ <b>username канала</b> (например: <code>@pepeksey</code>)\n\n"
                        "👤 Если <b>отправитель</b> <code>Юзербот</code> введите:\n"
                        "➤ <b>username пользователя</b> (например: <code>@leozizu</code>)\n"
                        "➤ <b>username канала</b> (например: <code>@pepeksey</code>)\n\n"
                        "🔎 <b>Узнать ID пользователя</b> можно тут: @userinfobot\n\n"
                        "⚠️ Чтобы аккаунт <code>Юзербота</code> отправил подарок на другой аккаунт, между аккаунтами должна быть переписка.\n\n"
                        "/cancel — отмена")
        await message.answer(message_text)
        await state.set_state(ConfigWizard.user_id)
    except ValueError:
        await message.answer("🚫 Введите положительное число. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.callback_query(F.data == "deposit_menu")
async def deposit_menu(call: CallbackQuery, state: FSMContext):
    """
    Переход к шагу пополнения баланса.
    """
    config = await get_valid_config(call.from_user.id)
    deposit_enabled = config.get("DEPOSIT_ENBALE", False)
    deposit_text = "🔋 Пополнение с других аккаунтов <b>разрешено</b>." if deposit_enabled else "🪫 Пополнение с других аккаунтов <b>запрещено</b>."
    button_text = "🪫 Запретить пополнение другим" if deposit_enabled else "🔋 Разрешить пополнение другим"
    button_callback = "deposit_disable" if deposit_enabled else "deposit_enable"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text, callback_data=button_callback)],
        ]
    )
    await call.message.answer(
        "💰 Введите сумму для пополнения, например: <code>5000</code>\n\n"
        f"{deposit_text}\n\n"
        "/cancel — отмена",
        reply_markup=keyboard
    )
    await state.set_state(ConfigWizard.deposit_amount)
    await call.answer()


@wizard_router.callback_query(F.data == "deposit_enable")
async def deposit_enable_handler(call: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Разрешить пополнение другим" в меню пополнения баланса.
    Включает возможность пополнения баланса с других аккаунтов для пользователя.
    Обновляет конфиг пользователя, сохраняет изменения и обновляет интерфейс с новым статусом.
    """
    config = await get_valid_config(call.from_user.id)
    config["DEPOSIT_ENBALE"] = True
    deposit_text = "🔋 Пополнение с других аккаунтов <b>разрешено</b>."
    await save_config(config)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🪫 Запретить пополнение другим", callback_data="deposit_disable")],
        ]
    )
    await call.message.edit_text(
        "💰 Введите сумму для пополнения, например: <code>5000</code>\n\n"
        f"{deposit_text}\n\n"
        "/cancel — отмена",
        reply_markup=keyboard)
    await call.answer()

@wizard_router.callback_query(F.data == "deposit_disable")
async def deposit_disable_handler(call: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Запретить пополнение другим" в меню пополнения баланса.
    Отключает возможность пополнения баланса с других аккаунтов для пользователя.
    Обновляет конфиг пользователя, сохраняет изменения и обновляет интерфейс с новым статусом.
    """
    config = await get_valid_config(call.from_user.id)
    config["DEPOSIT_ENBALE"] = False
    deposit_text = "🪫 Пополнение с других аккаунтов <b>запрещено</b>."
    await save_config(config)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔋 Разрешить пополнение другим", callback_data="deposit_enable")],
        ]
    )
    await call.message.edit_text(
        "💰 Введите сумму для пополнения, например: <code>5000</code>\n\n"
        f"{deposit_text}\n\n"
        "/cancel — отмена",
        reply_markup=keyboard)
    await call.answer()


@wizard_router.message(ConfigWizard.deposit_amount)
async def deposit_amount_input(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем суммы для пополнения баланса.
    Проверяет корректность введённой суммы, формирует и отправляет счёт на оплату через Telegram Payments.
    После успешного ввода очищает состояние FSM.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return

    try:
        amount = int(message.text)
        if amount < 1 or amount > 50000:
            raise ValueError
        prices = [LabeledPrice(label=CURRENCY, amount=amount)]
        await message.answer_invoice(
            title="Бот для подарков",
            description="Пополнение баланса",
            prices=prices,
            provider_token="",
            payload="stars_deposit",
            currency=CURRENCY,
            start_parameter="deposit",
            reply_markup=payment_keyboard(amount=amount),
        )
        await state.clear()
    except ValueError:
        await message.answer("🚫 Введите число от 1 до 50000. Попробуйте ещё раз.\n\n/cancel — отмена")


@wizard_router.callback_query(F.data == "refund_menu")
async def refund_menu(call: CallbackQuery, state: FSMContext):
    """
    Обработчик перехода к меню возврата звёзд по ID транзакции.
    Показывает пользователю инструкции по возврату, дополнительные команды и переводит FSM в соответствующее состояние.
    """
    await call.message.answer("↩️ <b>Вывод звёзд с</b> <code>Бота</code>.\n\n"
                              "📤 Отправьте в следующем сообщении <b>ID транзакции</b>.\n\n"
                              "🛠 Дополнительные возможности:\n\n"
                              "/withdraw_all — вывести весь баланс.\n\n"
                              "/refund + <code>[user_id]</code> + <code>[transaction_id]</code> — вернуть звёзды конкретному пользователю по <b>id транзакции</b>. Например: <code>/refund 12345678 abCdEF1g23hkL</code>\n\n"
                              "🚫 Вывести звёзды с <code>Юзербота</code> нельзя.\n\n"
                              "/cancel — отмена")
    await state.set_state(ConfigWizard.refund_id)
    await call.answer()


@wizard_router.message(ConfigWizard.refund_id)
async def refund_input(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем ID транзакции для возврата звёзд.
    Поддерживает команды /withdraw_all (вывод всего баланса) и /refund (возврат по конкретному пользователю и транзакции).
    Проверяет корректность данных, выполняет возврат и обновляет меню пользователя.
    """
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    if message.text and message.text.strip().lower() == "/withdraw_all":
        await state.clear()
        await withdraw_all_handler(message)
        return
    
    if message.text and "/refund" in message.text.strip().lower():
        await state.clear()
        await refund_handler(message)
        return
    
    if await try_cancel(message, state):
        return

    txn_id = message.text.strip()
    try:
        await message.bot.refund_star_payment(
            user_id=message.from_user.id,
            telegram_payment_charge_id=txn_id
        )
        await message.answer("✅ Возврат успешно выполнен.")
        balance = await refresh_balance(message.bot)
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
    except Exception as e:
        await message.answer(f"🚫 Ошибка при возврате:\n<code>{e}</code>")
    await state.clear()


@wizard_router.callback_query(F.data == "guest_deposit_menu")
async def guest_deposit_menu(call: CallbackQuery, state: FSMContext):
    """
    Обработчик перехода к шагу пополнения баланса для гостевых пользователей.
    Проверяет разрешение на пополнение для гостей, показывает форму ввода суммы и переводит FSM в соответствующее состояние.
    """
    if not await get_deposit_enabled():
        await call.message.answer("🚫 Пополнение баланса для гостей на данный момент запрещено администратором бота.")
        await call.answer()
        return

    await call.message.answer("💰 Введите сумму для пополнения, например: <code>5000</code>")
    await state.set_state(ConfigWizard.guest_deposit_amount)
    await call.answer()


@wizard_router.message(ConfigWizard.guest_deposit_amount)
async def guest_deposit_amount_input(message: Message, state: FSMContext):
    """
    Обрабатывает ввод суммы для пополнения баланса гостем.
    Проверяет корректность суммы, формирует и отправляет счёт на оплату через Telegram Payments.
    В случае ошибки показывает гостевое меню и сообщение об ошибке.
    """
    if not message.text:
        await show_guest_menu(message)
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n⚠️ Операция завершена, попробуйте заново.")
        return

    try:
        amount = int(message.text)
        if amount < 1 or amount > 50000:
            raise ValueError
        prices = [LabeledPrice(label=CURRENCY, amount=amount)]
        await message.answer_invoice(
            title="Бот для подарков",
            description="Пополнение баланса",
            prices=prices,
            provider_token="",
            payload="stars_deposit",
            currency=CURRENCY,
            start_parameter="deposit",
            reply_markup=payment_keyboard(amount=amount),
        )
        await state.clear()
    except ValueError:
        await state.clear()
        await show_guest_menu(message)
        await message.answer("🚫 Ожидается число от 1 до 50000.\n\n⚠️ Операция завершена, попробуйте заново.")
        

@wizard_router.message(Command("withdraw_all"))
async def withdraw_all_handler(message: Message):
    """
    Обрабатывает команду /withdraw_all для вывода всех звёзд с баланса пользователя.
    Проверяет права пользователя, баланс, формирует клавиатуру подтверждения и отправляет пользователю запрос на подтверждение действия.
    """
    allowed_user_ids = get_allowed_users()
    if message.from_user.id not in allowed_user_ids:
        await show_guest_menu(message)
        return

    balance = await refresh_balance(message.bot)
    if balance == 0:
        await message.answer("⚠️ Не найдено звёзд для возврата.")
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data="withdraw_all_confirm"),
                InlineKeyboardButton(text="❌ Нет", callback_data="withdraw_all_cancel"),
            ]
        ]
    )
    await message.answer(
        "⚠️ Вы уверены, что хотите вывести все звёзды?",
        reply_markup=keyboard,
    )


@wizard_router.callback_query(lambda c: c.data == "withdraw_all_confirm")
async def withdraw_all_confirmed(call: CallbackQuery) -> None:
    """
    Обработчик подтверждения возврата всех звёзд.
    Запускает процедуру возврата, отправляет промежуточные статусы, формирует итоговый отчёт о возврате и обновляет меню пользователя.
    """
    await call.message.edit_text("⏳ Выполняется вывод звёзд...")

    async def send_status(msg: str) -> None:
        """
        Отправляет сообщение статуса пользователю при возврате звёзд.
        Логирует ошибки отправки.
        """
        try:
            await call.message.answer(msg)
        except Exception as e:
            logger.error(f"Ошибка при отправке статуса: {e}")

    await call.answer()

    result = await refund_all_star_payments(
        bot=call.bot,
        user_id=call.from_user.id,
        username=call.from_user.username,
        message_func=send_status,
    )
    if result["count"] > 0:
        msg = f"✅ Возвращено: ★{result['refunded']}\n🔄 Транзакций: {result['count']}"
        if result["left"] > 0:
            msg += f"\n💰 Остаток звёзд: {result['left']}"
            dep = result.get("next_deposit")
            if dep:
                need = dep['amount'] - result['left']
                msg += (
                    f"\n➕ Пополните баланс ещё минимум на ★{need} (или суммарно до ★{dep['amount']})."
                )
        await call.message.answer(msg)
    else:
        await call.message.answer("🚫 Звёзд для возврата не найдено.")

    balance = await refresh_balance(call.bot)
    await update_menu(bot=call.bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


@wizard_router.callback_query(lambda c: c.data == "withdraw_all_cancel")
async def withdraw_all_cancel(call: CallbackQuery) -> None:
    """
    Обработчик отмены процедуры возврата всех звёзд.
    Обновляет сообщение, завершает действие и возвращает пользователя к основному меню.
    """
    await call.message.edit_text("🚫 Действие отменено.")
    await call.answer()
    await update_menu(bot=call.bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


@wizard_router.message(Command("refund"))
async def refund_handler(message: Message) -> None:
    """
    Обрабатывает команду /refund для возврата звёзд по конкретной транзакции и пользователю.
    Проверяет права пользователя, корректность формата команды, выполняет возврат и обновляет меню пользователя.
    В случае ошибки выводит подробное сообщение.
    """
    allowed_user_ids = get_allowed_users()
    if message.from_user.id not in allowed_user_ids:
        await show_guest_menu(message)
        return
    
    if await try_cancel(message, None):
        return
    
    parts = message.text.strip().split()

    if len(parts) != 3:
        await message.answer(
            "🚫 Неправильный формат команды."
        )
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
        return

    _, user_id_str, txn_id = parts

    try:
        user_id = int(user_id_str)
    except ValueError:
        await message.answer("🚫 Неверный формат <code>[user_id]</code>. Используйте целое число.")
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
        return

    try:
        await message.bot.refund_star_payment(
            user_id=user_id,
            telegram_payment_charge_id=txn_id
        )
        await message.answer(f"✅ Возврат по транзакции <code>{txn_id}</code> для пользователя <code>{user_id}</code> выполнен.")
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
    except Exception as e:
        error_text = str(e)
        short_error = error_text.split(":")[-1].strip()
        await message.answer(f"🚫 Ошибка при возврате по транзакции <code>{txn_id}</code>:\n\n<code>{short_error}</code>")
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)


# ------------- Дополнительные функции ---------------------


async def try_cancel(message: Message, state: FSMContext) -> bool:
    """
    Проверяет, ввёл ли пользователь команду /cancel для отмены текущего шага мастера.
    Если команда введена, очищает состояние FSM, отправляет сообщение об отмене и обновляет главное меню пользователя.
    Возвращает True, если отмена была выполнена, иначе False.
    """
    if message.text and message.text.strip().lower() == "/cancel":
        await state.clear()
        await message.answer("🚫 Действие отменено.")
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
        return True
    return False


async def get_chat_type(bot: Bot, username: str) -> str:
    """
    Определяет тип Telegram-объекта (user, bot, channel, group) по username.
    Используется для проверки корректности получателя подарка при настройке профиля.
    В случае ошибки возвращает "unknown" и логирует причину.
    """
    if not username.startswith("@"):
        username = "@" + username
    try:
        chat = await bot.get_chat(username)
        if chat.type == "private":
            if getattr(chat, "is_bot", False):
                return "bot"
            else:
                return "user"
        elif chat.type == "channel":
            return "channel"
        elif chat.type in ("group", "supergroup"):
            return "group"
        else:
            return chat.type
    except TelegramAPIError as e:
        logger.info(f"TelegramAPIError при получении юзернейма канала (введён username пользователя): {e}")
        return "unknown"
    except Exception as e:
        logger.info(f"Ошибка при получении юзернейма канала (введён username пользователя): {e}")
        return "unknown"
    

def register_wizard_handlers(dp: Dispatcher) -> None:
    """
    Регистрирует маршрутизатор wizard_router в диспетчере событий Telegram-бота.
    Позволяет использовать все обработчики мастера профилей и связанных функций.
    """
    dp.include_router(wizard_router)
