# --- Стандартные библиотеки ---
import asyncio

# --- Сторонние библиотеки ---
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

# --- Внутренние модули ---
from services.config import get_target_display_local
from services.menu import update_menu
from services.gifts import get_filtered_gifts
from services.buy import buy_gift
from services.balance import refresh_balance

wizard_router = Router()

class CatalogFSM(StatesGroup):
    """
    Состояния для FSM каталога подарков.
    """
    waiting_gift = State()
    waiting_quantity = State()
    waiting_recipient = State()
    waiting_confirm = State()


def gifts_catalog_keyboard(gifts):
    """
    Формирует клавиатуру для каталога подарков. 
    Каждый подарок — отдельная кнопка, плюс кнопка возврата в меню.
    """
    keyboard = []
    for gift in gifts:
        if gift['supply'] == None:
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
            text="☰ Вернуться в меню", 
            callback_data="catalog_main_menu"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@wizard_router.callback_query(F.data == "catalog")
async def catalog(call: CallbackQuery, state: FSMContext):
    """
    Обработка открытия каталога. Получает список подарков и формирует сообщение с клавиатурой.
    """
    gifts = await get_filtered_gifts(
        bot=call.bot,
        min_price=0,
        max_price=1000000,
        min_supply=0,
        max_supply=100000000,
        unlimited = True
    )

    # Сохраняем текущий каталог в FSM — нужен для последующих шагов
    await state.update_data(gifts_catalog=gifts)

    gifts_limited = [g for g in gifts if g['supply'] != None]
    gifts_unlimited = [g for g in gifts if g['supply'] == None]

    await call.message.answer(
        f"🧸 Обычных подарков: <b>{len(gifts_unlimited)}</b>\n"
        f"👜 Уникальных подарков: <b>{len(gifts_limited)}</b>\n",
        reply_markup=gifts_catalog_keyboard(gifts)
    )

    await call.answer()


@wizard_router.callback_query(F.data == "catalog_main_menu")
async def start_callback(call: CallbackQuery, state: FSMContext):
    """
    Показывает главное меню по нажатию кнопки "Вернуться в меню".
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
async def on_gift_selected(call: CallbackQuery, state: FSMContext):
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

    gift_display = f"{gift['left']:,} из {gift['supply']:,}" if gift.get("supply") != None else gift.get("emoji")

    await state.update_data(selected_gift=gift)
    await call.message.edit_text(
        f"🎯 Вы выбрали: <b>{gift_display}</b> за ★{gift['price']}\n"
        f"🎁 Введите <b>количество</b> для покупки:\n\n"
        f"/cancel - для отмены",
        reply_markup=None
    )
    await state.set_state(CatalogFSM.waiting_quantity)
    await call.answer()


@wizard_router.message(CatalogFSM.waiting_quantity)
async def on_quantity_entered(message: Message, state: FSMContext):
    """
    Хендлер обработки ввода количества для покупки выбранного подарка.
    Теперь переходим к шагу ввода получателя.
    """
    if await try_cancel(message, state):
        return
    
    try:
        qty = int(message.text)
        if qty <= 0:
            raise ValueError
    except Exception:
        await message.answer("🚫 Введите целое положительное число!")
        return
    
    await state.update_data(selected_qty=qty)

    await message.answer(
        "👤 Введите получателя подарка:\n\n"
        f"• <b>ID пользователя</b> (например ваш: <code>{message.from_user.id}</code>)\n"
        "• Или <b>username канала</b> (например: <code>@channel</code>)\n\n"
        "❗️ Узнать ID пользователя тут @userinfobot\n\n"
        "/cancel — отменить"
    )
    await state.set_state(CatalogFSM.waiting_recipient)


@wizard_router.message(CatalogFSM.waiting_recipient)
async def on_recipient_entered(message: Message, state: FSMContext):
    """
    Обработка ввода получателя (ID пользователя или username канала).
    """
    if await try_cancel(message, state):
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

    data = await state.get_data()
    gift = data["selected_gift"]
    qty = data["selected_qty"]
    price = gift.get("price")
    total = price * qty

    gift_display = f"{gift['left']:,} из {gift['supply']:,}" if gift.get("supply") != None else gift.get("emoji")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_purchase"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_purchase"),
            ]
        ]
    )
    recipient_display = get_target_display_local(target_user_id, target_chat_id, message.from_user.id)
    await message.answer(
        f"📦 Подарок: <b>{gift_display}</b>\n"
        f"🎁 Количество: <b>{qty}</b>\n"
        f"💵 Цена подарка: <b>★{price:,}</b>\n"
        f"💰 Общая сумма: <b>★{total:,}</b>\n"
        f"👤 Получатель: {recipient_display}",
        reply_markup=kb
    )
    await state.set_state(CatalogFSM.waiting_confirm)


@wizard_router.callback_query(F.data == "confirm_purchase")
async def confirm_purchase(call: CallbackQuery, state: FSMContext):
    """
    Подтверждение и запуск покупки выбранного подарка в заданном количестве для выбранного получателя.
    """
    data = await state.get_data()
    gift = data["selected_gift"]
    if not gift:
        await call.answer("🚫 Запрос на покупку не актуален. Пожалуйста, попробуйте снова.", show_alert=True)
        await safe_edit_text(call.message, "🚫 Запрос на покупку не актуален. Пожалуйста, попробуйте снова.", reply_markup=None)
        return
    await call.message.edit_text(text="⏳ Выполняется покупка подарков...", reply_markup=None)
    gift_id = gift.get("id")
    gift_price = gift.get("price")
    qty = data["selected_qty"]
    target_user_id=data.get("target_user_id")
    target_chat_id=data.get("target_chat_id")
    gift_display = f"{gift['left']:,} из {gift['supply']:,}" if gift.get("supply") != None else gift.get("emoji")

    bought = 0
    while bought < qty:
        success = await buy_gift(
            bot=call.bot,
            env_user_id=call.from_user.id,
            gift_id=gift_id,
            user_id=target_user_id,
            chat_id=target_chat_id,
            gift_price=gift_price,
            file_id=None
        )

        if not success:
            break

        bought += 1
        await asyncio.sleep(0.3)

    if bought == qty:
        await call.message.answer(f"✅ Покупка <b>{gift_display}</b> успешно завершена!\n"
                                  f"🎁 Куплено подарков: <b>{bought}</b> из <b>{qty}</b>\n"
                                  f"👤 Получатель: {get_target_display_local(target_user_id, target_chat_id, call.from_user.id)}")
    else:
        await call.message.answer(f"⚠️ Покупка <b>{gift_display}</b> остановлена.\n"
                                  f"🎁 Куплено подарков: <b>{bought}</b> из <b>{qty}</b>\n"
                                  f"👤 Получатель: {get_target_display_local(target_user_id, target_chat_id, call.from_user.id)}\n"
                                  f"💰 Пополните баланс!\n"
                                  f"📦 Проверьте доступность подарка!\n"
                                  f"🚦 Статус изменён на 🔴 (неактивен).")
    
    await state.clear()
    await call.answer()
    await update_menu(bot=call.bot, chat_id=call.message.chat.id, user_id=call.from_user.id, message_id=call.message.message_id)


@wizard_router.callback_query(lambda c: c.data == "cancel_purchase")
async def cancel_callback(call: CallbackQuery, state: FSMContext):
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


async def safe_edit_text(message, text, reply_markup=None):
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


def register_catalog_handlers(dp):
    """
    Регистрирует все хендлеры, связанные с каталогом подарков.
    """
    dp.include_router(wizard_router)
