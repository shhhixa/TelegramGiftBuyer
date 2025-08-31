"""
Модуль хендлеров для каталога подарков.

Этот модуль содержит функции для:
- Управления состояниями FSM каталога подарков.
- Формирования клавиатуры для каталога подарков.
- Обработки выбора подарков, количества, получателя и отправителя.
- Подтверждения и выполнения покупки подарков.
- Отмены действий и возврата в главное меню.

Основные функции:
- catalog: Открывает каталог подарков.
- on_gift_selected: Обрабатывает выбор подарка.
- on_quantity_entered: Обрабатывает ввод количества.
- on_recipient_entered: Обрабатывает ввод получателя.
- on_catalog_sender_selected: Обрабатывает выбор отправителя.
- confirm_purchase: Подтверждает и выполняет покупку.
- cancel_callback: Отменяет покупку.
- try_cancel: Универсальная функция для обработки отмены.
- safe_edit_text: Безопасно редактирует текст сообщения.
"""

# --- Стандартные библиотеки ---
import asyncio

# --- Сторонние библиотеки ---
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

# --- Внутренние модули ---
from services.config import get_target_display_local, PURCHASE_COOLDOWN
from services.menu import update_menu
from services.gifts_manager import get_best_gift_list
from services.buy_bot import buy_gift
from services.buy_userbot import buy_gift_userbot
from services.balance import refresh_balance

wizard_router = Router() # Роутер для FSM каталога

class CatalogFSM(StatesGroup):
    """
    Состояния для FSM каталога подарков.
    """
    waiting_gift = State()
    waiting_quantity = State()
    waiting_recipient = State()
    waiting_sender = State()
    waiting_confirm = State()


def gifts_catalog_keyboard(gifts: list[dict]) -> InlineKeyboardMarkup:
    """
    Формирует клавиатуру для каталога подарков. 
    Каждый подарок — отдельная кнопка, плюс кнопка возврата в меню.
    """
    keyboard = []
    for gift in gifts:
        if gift['supply'] == 0:
            btn = InlineKeyboardButton(
                text=f"{gift['emoji']} — ★{gift['price']:,}",
                callback_data=f"catalog_gift_{gift['id']}"
            )
        else:
            btn = InlineKeyboardButton(
                text=f"{gift['left']:,} из {gift['supply']:,} — ★{gift['price']:,}",
                callback_data=f"catalog_gift_{gift['id']}"
            )
        keyboard.append([btn])

    # Кнопка для возврата в главное меню
    keyboard.append([
        InlineKeyboardButton(
            text="☰ Меню", 
            callback_data="catalog_main_menu"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@wizard_router.callback_query(F.data == "catalog")
async def catalog(call: CallbackQuery, state: FSMContext) -> None:
    """
    Обработка открытия каталога. Получает список подарков и формирует сообщение с клавиатурой.
    """
    gifts = await get_best_gift_list(
        user_id=call.from_user.id,
        bot=call.bot,
        profile={
            "MIN_PRICE": 0, 
            "MAX_PRICE": 1000000,
            "MIN_SUPPLY": 0,
            "MAX_SUPPLY": 100000000,
            "UNLIMITED": True
        }
    )

    # Сохраняем текущий каталог в FSM — нужен для последующих шагов
    await state.update_data(gifts_catalog=gifts)

    gifts_limited = [g for g in gifts if g['supply'] > 0]
    gifts_unlimited = [g for g in gifts if g['supply'] == 0]

    await call.message.answer(
        f"🧸 Обычных подарков: <b>{len(gifts_unlimited)}</b>\n"
        f"👜 Уникальных подарков: <b>{len(gifts_limited)}</b>\n",
        reply_markup=gifts_catalog_keyboard(gifts)
    )

    await call.answer()


@wizard_router.callback_query(F.data == "catalog_main_menu")
async def start_callback(call: CallbackQuery, state: FSMContext) -> None:
    """
    Показывает главное меню по нажатию кнопки "Меню".
    Очищает все состояния FSM для пользователя.
    """
    await state.clear()
    await call.answer()
    await safe_edit_text(call.message, "🚫 Каталог закрыт.", reply_markup=None)
    await refresh_balance(call.bot)
    await update_menu(
        bot=call.bot,
        chat_id=call.message.chat.id,
        user_id=call.from_user.id,
        message_id=call.message.message_id
    )


@wizard_router.callback_query(F.data.startswith("catalog_gift_"))
async def on_gift_selected(call: CallbackQuery, state: FSMContext) -> None:
    """
    Хендлер выбора подарка из каталога. Запрашивает у пользователя количество для покупки.
    """
    gift_id = call.data.split("_")[-1]
    data = await state.get_data()
    gifts = data.get("gifts_catalog", [])
    if not gifts:
        await call.answer("🚫 Каталог устарел. Откройте заново.", show_alert=True)
        await safe_edit_text(call.message, "🚫 Каталог устарел. Откройте заново.", reply_markup=None)
        return
    gift = next((g for g in gifts if str(g['id']) == gift_id), None)

    gift_display = f"{gift['left']:,} из {gift['supply']:,}" if gift.get("supply") != 0 else gift.get("emoji")

    await state.update_data(selected_gift=gift)
    await call.message.edit_text(
        f"🎯 Вы выбрали: <b>{gift_display}</b> за ★{gift['price']}\n"
        f"🎁 Введите <b>количество</b> для покупки:\n\n"
        f"/cancel — отмена",
        reply_markup=None
    )
    await state.set_state(CatalogFSM.waiting_quantity)
    await call.answer()


@wizard_router.message(CatalogFSM.waiting_quantity)
async def on_quantity_entered(message: Message, state: FSMContext) -> None:
    """
    Хендлер обработки ввода количества для покупки выбранного подарка.
    Теперь переходим к шагу ввода получателя.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return
    
    try:
        qty = int(message.text)
        if qty <= 0:
            raise ValueError
    except Exception:
        await message.answer("🚫 Введите целое положительное число!\n\n/cancel — отмена")
        return
    
    await state.update_data(selected_qty=qty)

    message_text = ("📥 Введите <b>получателя</b> подарка:\n\n"
                    "🤖 Если <b>отправитель</b> <code>Бот</code> введите:\n"
                    f"➤ <b>ID пользователя</b> (например ваш: <code>{message.from_user.id}</code>)\n"
                    "➤ <b>username канала</b> (например: <code>@pepeksey</code>)\n\n"
                    "👤 Если <b>отправитель</b> <code>Юзербот</code> введите:\n"
                    "➤ <b>username</b> пользователя (например: <code>@leozizu</code>)\n"
                    "➤ <b>username</b> канала (например: <code>@pepeksey</code>)\n\n"
                    "🔎 <b>Узнать ID пользователя</b> можно тут: @userinfobot\n"
                    "⚠️ Чтобы аккаунт <code>Юзербота</code> отправил подарок на другой аккаунт, между аккаунтами должна быть переписка.\n\n"
                    "/cancel — отмена")
    await message.answer(message_text)
    await state.set_state(CatalogFSM.waiting_recipient)


@wizard_router.message(CatalogFSM.waiting_recipient)
async def on_recipient_entered(message: Message, state: FSMContext) -> None:
    """
    Обрабатывает ввод получателя — ID или username.
    """
    if await try_cancel(message, state):
        return
    
    if not message.text:
        await message.answer("🚫 Поддерживается только текстовый ввод данных.\n\n/cancel — отмена")
        return

    user_input = message.text.strip()
    if user_input.startswith("@"):
        target_chat_id = user_input
        target_user_id = None
    elif user_input.isdigit():
        target_chat_id = None
        target_user_id = int(user_input)
    else:
        await message.answer(
            "🚫 Если получатель аккаунт — введите ID, если канал — username с @. Попробуйте ещё раз."
        )
        return

    await state.update_data(
        target_user_id=target_user_id,
        target_chat_id=target_chat_id
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Бот", callback_data="catalog_sender_bot"),
                InlineKeyboardButton(text="👤 Юзербот", callback_data="catalog_sender_userbot"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_purchase")]
        ]
    )
    message_text = ("📤 Выберите <b>отправителя</b> подарков:\n\n"
                    "🤖 <code>Бот</code> - покупки с баланса бота\n"
                    "👤 <code>Юзербот</code> - покупки с баланса юзербота\n\n"
                    "/cancel — отмена")
    await message.answer(message_text, reply_markup=kb)
    await state.set_state(CatalogFSM.waiting_sender)


@wizard_router.callback_query(F.data.startswith("catalog_sender_"))
async def on_catalog_sender_selected(call: CallbackQuery, state: FSMContext) -> None:
    """
    Обрабатывает выбор отправителя (бот или юзербот).
    """
    sender = call.data.replace("catalog_sender_", "")
    await state.update_data(sender=sender)
    await call.answer("✅ Отправитель выбран.")

    data = await state.get_data()
    gift = data["selected_gift"]
    qty = data["selected_qty"]
    price = gift.get("price")
    total = price * qty
    target_user_id = data.get("target_user_id")
    target_chat_id = data.get("target_chat_id")

    gift_display = f"{gift['left']:,} из {gift['supply']:,}" if gift.get("supply") != 0 else gift.get("emoji")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_purchase"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_purchase"),
            ]
        ]
    )

    recipient_display = get_target_display_local(target_user_id, target_chat_id, call.from_user.id)

    await call.message.edit_text(
        f"📦 Подарок: <b>{gift_display}</b>\n"
        f"🎁 Количество: <b>{qty}</b>\n"
        f"💵 Цена подарка: <b>★{price:,}</b>\n"
        f"💰 Общая сумма: <b>★{total:,}</b>\n"
        f"👤 Получатель: {recipient_display}\n"
        f"📤 Отправитель: {'🤖 Бот' if sender == 'bot' else '👤 Юзербот'}",
        reply_markup=kb
    )

    await state.set_state(CatalogFSM.waiting_confirm)


@wizard_router.callback_query(F.data == "confirm_purchase")
async def confirm_purchase(call: CallbackQuery, state: FSMContext) -> None:
    """
    Подтверждение и запуск покупки выбранного подарка в заданном количестве для выбранного получателя.
    """
    data = await state.get_data()
    sender = data["sender"]
    gift = data["selected_gift"]
    if not gift:
        await call.answer("🚫 Запрос на покупку не актуален. Пожалуйста, попробуйте снова.", show_alert=True)
        await safe_edit_text(call.message, "🚫 Запрос на покупку не актуален. Пожалуйста, попробуйте снова.", reply_markup=None)
        return
    await call.message.edit_text(text="⏳ Выполняется покупка подарков...", reply_markup=None)
    gift_id = gift.get("id")
    gift_price = gift.get("price")
    qty = data["selected_qty"]
    data_target_user_id=data.get("target_user_id")
    data_target_chat_id=data.get("target_chat_id")
    gift_display = f"{gift['left']:,} из {gift['supply']:,}" if gift.get("supply") != 0 else gift.get("emoji")

    bought = 0
    while bought < qty:
        if sender == 'bot':
            success = await buy_gift(
                bot=call.bot,
                env_user_id=call.from_user.id,
                gift_id=gift_id,
                target_user_id=data_target_user_id,
                target_chat_id=data_target_chat_id,
                gift_price=gift_price,
                file_id=None
            )
        elif sender == 'userbot':
            success = await buy_gift_userbot(
                session_user_id=call.from_user.id,
                gift_id=gift_id,
                target_user_id=data_target_user_id,
                target_chat_id=data_target_chat_id,
                gift_price=gift_price,
                file_id=None
            )
        else:
            success = False

        if not success:
            break

        bought += 1
        await asyncio.sleep(PURCHASE_COOLDOWN)

    if bought == qty:
        await call.message.answer(f"✅ Покупка <b>{gift_display}</b> успешно завершена!\n"
                                  f"🎁 Куплено подарков: <b>{bought}</b> из <b>{qty}</b>\n"
                                  f"👤 Получатель: {get_target_display_local(data_target_user_id, data_target_chat_id, call.from_user.id)}")
    else:
        await call.message.answer(f"⚠️ Покупка <b>{gift_display}</b> остановлена.\n"
                                  f"🎁 Куплено подарков: <b>{bought}</b> из <b>{qty}</b>\n"
                                  f"👤 Получатель: {get_target_display_local(data_target_user_id, data_target_chat_id, call.from_user.id)}\n"
                                  "💰 Пополните баланс! Проверьте адрес получателя!\n"
                                  "📦 Проверьте доступность подарка!\n"
                                  "🪜 Проверьте типы принимаемых подарков у получателя!\n"
                                  f"🚦 Статус изменён на 🔴 (неактивен).")
    
    await state.clear()
    await call.answer()
    await update_menu(bot=call.bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


@wizard_router.callback_query(lambda c: c.data == "cancel_purchase")
async def cancel_callback(call: CallbackQuery, state: FSMContext) -> None:
    """
    Отмена покупки подарка на этапе подтверждения.
    """
    await state.clear()
    await call.answer()
    await safe_edit_text(call.message, "🚫 Действие отменено.", reply_markup=None)
    await update_menu(bot=call.bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


async def try_cancel(message: Message, state: FSMContext) -> bool:
    """
    Универсальная функция для обработки отмены любого шага с помощью /cancel.
    Очищает состояние, возвращает True если была отмена.
    """
    if message.text and message.text.strip().lower() == "/cancel":
        await state.clear()
        await message.answer("🚫 Действие отменено.")
        await update_menu(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id, message_id=message.message_id)
        return True
    return False


async def safe_edit_text(message: Message, text: str, reply_markup: InlineKeyboardMarkup = None) -> bool:
    """
    Безопасно редактирует текст сообщения, игнорируя ошибки "нельзя редактировать" и "сообщение не найдено".
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        if "message can't be edited" in str(e) or "message to edit not found" in str(e):
            # Просто игнорируем — сообщение устарело или удалено
            return False
        else:
            raise


def register_catalog_handlers(dp) -> None:
    """
    Регистрирует все хендлеры, связанные с каталогом подарков.
    """
    dp.include_router(wizard_router)
