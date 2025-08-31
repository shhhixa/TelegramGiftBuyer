"""
Модуль работы с балансом звёзд.

Этот модуль содержит функции для:
- Получения текущего баланса звёзд через API бота.
- Обновления баланса звёзд в конфиге.
- Изменения баланса звёзд с учётом ограничений.
- Возврата звёзд по депозитам без возврата.

Основные функции:
- get_stars_balance: Получает текущий баланс звёзд через API бота.
- refresh_balance: Обновляет баланс звёзд в конфиге.
- change_balance: Изменяет баланс звёзд в конфиге.
- refund_all_star_payments: Возвращает звёзды по депозитам без возврата.
"""

# --- Стандартные библиотеки ---
from itertools import combinations
import logging
from typing import Callable, Awaitable, Any

# --- Внутренние модули ---
from services.config import load_config, save_config
from services.userbot import get_userbot_stars_balance

# --- Сторонние библиотеки ---
from aiogram import Bot
from aiogram.types.star_amount import StarAmount

logger = logging.getLogger(__name__)

async def get_stars_balance(bot: Bot) -> int:
    """
    Получает текущий баланс звёзд через API бота.
    :param bot: Экземпляр бота
    :return: Баланс звёзд (int)
    """
    star_amount: StarAmount = await bot.get_my_star_balance()
    balance = star_amount.amount

    return balance


async def get_stars_balance_by_transactions(bot: Bot) -> int:
    """
    Получает баланс звёзд по всем транзакциям пользователя через API бота (устаревший метод).
    :param bot: Экземпляр бота
    :return: Баланс звёзд (int)
    """
    offset = 0
    limit = 100
    balance = 0

    while True:
        get_transactions = await bot.get_star_transactions(offset=offset, limit=limit)
        transactions = get_transactions.transactions

        if not transactions:
            break

        for transaction in transactions:
            source = transaction.source
            amount = transaction.amount
            if source is not None:
                balance += amount
            else:
                balance -= amount

        offset += limit

    return balance


async def refresh_balance(bot: Bot) -> int:
    """
    Обновляет баланс звёзд в конфиге и возвращает актуальное значение.
    :param bot: Экземпляр бота
    :return: Баланс звёзд (int)
    """
    # Загрузка конфига
    config = await load_config()
    userbot_data = config.get("USERBOT", {})

    # Баланс userbot-а (если сессия существует)
    has_session = (
        userbot_data.get("API_ID")
        and userbot_data.get("API_HASH")
        and userbot_data.get("PHONE")
    )
    if has_session:
        try:
            userbot_balance = await get_userbot_balance()
            config["USERBOT"]["BALANCE"] = userbot_balance
        except Exception as e:
            config["USERBOT"]["BALANCE"] = 0
            logger.error(f"Не удалось получить баланс userbot: {e}")
    else:
        logger.info("Userbot-сессия неактивна или не настроена.")
        config["USERBOT"]["BALANCE"] = 0

    # Баланс основного бота
    balance = await get_stars_balance(bot)
    config["BALANCE"] = balance

    # Сохраняем всё
    await save_config(config)
    return balance


async def change_balance(delta: int) -> int:
    """
    Изменяет баланс звёзд в конфиге на delta, не допуская отрицательных значений.
    :param delta: Изменение баланса (int)
    :return: Новый баланс (int)
    """
    config = await load_config()
    config["BALANCE"] = max(0, config.get("BALANCE", 0) + delta)
    balance = config["BALANCE"]
    await save_config(config)
    return balance


async def change_balance_userbot(delta: int) -> int:
    """
    Изменяет баланс звёзд юзербота в конфиге на delta, не допуская отрицательных значений.
    :param delta: Изменение баланса (int)
    :return: Новый баланс юзербота (int)
    """
    config = await load_config()
    userbot = config.get("USERBOT", {})
    current = userbot.get("BALANCE", 0)
    new_balance = max(0, current + delta)

    config["USERBOT"]["BALANCE"] = new_balance
    await save_config(config)
    return new_balance


async def refund_all_star_payments(
    bot: Bot,
    username: str,
    user_id: int,
    message_func: Callable[[str], Awaitable[Any]] = None
) -> dict:
    """
    Возвращает звёзды по депозитам без возврата, совершённым указанным username.
    Подбирает оптимальную комбинацию для вывода максимально возможной суммы.
    :param bot: Экземпляр бота
    :param username: Username пользователя
    :param user_id: ID пользователя
    :param message_func: Функция для отправки сообщений пользователю (опционально)
    :return: Словарь с результатами возврата
    """
    balance = await refresh_balance(bot)
    if balance <= 0:
        return {"refunded": 0, "count": 0, "txn_ids": [], "left": 0}

    # Получаем все транзакции
    offset = 0
    limit = 100
    all_txns = []
    while True:
        res = await bot.get_star_transactions(offset=offset, limit=limit)
        txns = res.transactions
        if not txns:
            break
        all_txns.extend(txns)
        offset += limit

    # Фильтруем депозиты без возврата и только с нужным username
    deposits = [
        t for t in all_txns
        if t.source is not None
        and getattr(t.source, "user", None)
        and getattr(t.source.user, "username", None) == username
    ]
    refunded_ids = {t.id for t in all_txns if t.source is None}
    unrefunded_deposits = [t for t in deposits if t.id not in refunded_ids]

    n = len(unrefunded_deposits)
    best_combo = []
    best_sum = 0

    # Ищем идеальную комбинацию или greedy
    if n <= 18:
        for r in range(1, n+1):
            for combo in combinations(unrefunded_deposits, r):
                s = sum(t.amount for t in combo)
                if s <= balance and s > best_sum:
                    best_combo = combo
                    best_sum = s
                if best_sum == balance:
                    break
            if best_sum == balance:
                break
    else:
        unrefunded_deposits.sort(key=lambda t: t.amount, reverse=True)
        curr_sum = 0
        best_combo = []
        for t in unrefunded_deposits:
            if curr_sum + t.amount <= balance:
                best_combo.append(t)
                curr_sum += t.amount
        best_sum = curr_sum

    if not best_combo:
        return {"refunded": 0, "count": 0, "txn_ids": [], "left": balance}

    # Делаем возвраты только по выбранным транзакциям
    total_refunded = 0
    refund_ids = []
    for txn in best_combo:
        txn_id = getattr(txn, "id", None)
        if not txn_id:
            continue
        try:
            await bot.refund_star_payment(
                user_id=user_id,
                telegram_payment_charge_id=txn_id
            )
            total_refunded += txn.amount
            refund_ids.append(txn_id)
        except Exception as e:
            if message_func:
                await message_func(f"🚫 Ошибка при возврате ★{txn.amount}")

    left = balance - best_sum

    # Находим транзакцию, которой хватит чтобы покрыть остаток
    # Берём минимальную сумму среди транзакций, где amount > min_needed
    def find_next_possible_deposit(unused_deposits, min_needed):
        bigger = [t for t in unused_deposits if t.amount > min_needed]
        if not bigger:
            return None
        best = min(bigger, key=lambda t: t.amount)
        return {"amount": best.amount, "id": getattr(best, "id", None)}

    unused_deposits = [t for t in unrefunded_deposits if t not in best_combo]
    next_possible = None
    if left > 0 and unused_deposits:
        next_possible = find_next_possible_deposit(unused_deposits, left)

    return {
        "refunded": total_refunded,
        "count": len(refund_ids),
        "txn_ids": refund_ids,
        "left": left,
        "next_deposit": next_possible
    }


async def get_userbot_balance() -> int:
    """
    Получает баланс звёзд у userbot-сессии.
    :return: Баланс юзербота (int)
    """
    return await get_userbot_stars_balance()
