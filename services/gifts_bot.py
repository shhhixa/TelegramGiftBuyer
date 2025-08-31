"""
Модуль работы с подарками через Bot API.

Этот модуль содержит функции для:
- Нормализации объектов подарков в словари.
- Получения и фильтрации списка подарков из Bot API.
- Генерации тестовых подарков для отладки.

Основные функции:
- normalize_gift: Преобразует объект Gift в словарь с основными характеристиками.
- get_bot_filtered_gifts: Получает и фильтрует список подарков из Bot API.
"""

# --- Стандартные библиотеки ---
import logging

# --- Сторонние библиотеки ---
from aiogram import Bot

# --- Внутренние модули ---
from utils.mockdata import generate_test_gifts
from services.config import DEV_MODE, MORE_LOGS

logger = logging.getLogger(__name__)

def normalize_gift(gift: object) -> dict:
    """
    Преобразует объект Gift в словарь с основными характеристиками подарка.

    :param gift: Объект Gift (любой тип с нужными атрибутами).
    :return: Словарь с параметрами подарка.
    """
    return {
        "id": getattr(gift, "id", None),
        "price": getattr(gift, "star_count", 0),
        "supply": getattr(gift, "total_count", 0) or 0,
        "left": getattr(gift, "remaining_count", 0) or 0,
        "sticker_file_id": getattr(getattr(gift, "sticker", None), "file_id", None),
        "emoji": getattr(getattr(gift, "sticker", None), "emoji", None),
    }


async def get_bot_filtered_gifts(
    bot: Bot,
    min_price: int,
    max_price: int,
    min_supply: int,
    max_supply: int,
    unlimited: bool = False,
    add_test_gifts: bool = False,
    test_gifts_count: int = 5
) -> list[dict]:
    """
    Получает и фильтрует список подарков из API, возвращает их в нормализованном виде.

    :param bot: Экземпляр бота aiogram.
    :param min_price: Минимальная цена подарка.
    :param max_price: Максимальная цена подарка.
    :param min_supply: Минимальный supply подарка.
    :param max_supply: Максимальный supply подарка.
    :param unlimited: Если True — игнорировать supply при фильтрации.
    :param add_test_gifts: Добавлять тестовые подарки в конец списка.
    :param test_gifts_count: Количество тестовых подарков.
    :return: Список словарей с параметрами подарков, отсортированный по цене по убыванию.
    """
    # Получаем, нормализуем и фильтруем подарки из маркета
    try:
        api_gifts = await bot.get_available_gifts()
        if MORE_LOGS: logger.info(f"Получено {len(api_gifts.gifts)} подарков из Bot API.")
    except Exception as e:
        logger.error(f"Ошибка при получении подарков из Bot API: {e}")
        return []
    
    filtered = []
    for gift in api_gifts.gifts:
        price_ok = min_price <= gift.star_count <= max_price
        # Логика по unlimited
        if unlimited:
            supply_ok = True
        else:
            supply = gift.total_count or 0
            supply_ok = min_supply <= supply <= max_supply
        if price_ok and supply_ok:
            filtered.append(gift)
    normalized = [normalize_gift(gift) for gift in filtered]

    # Получаем и фильтруем тестовые подарки отдельно
    test_gifts = []
    if add_test_gifts or DEV_MODE:
        test_gifts = generate_test_gifts(test_gifts_count)
        test_gifts = [
            gift for gift in test_gifts
            if min_price <= gift["price"] <= max_price and (
                unlimited or min_supply <= gift["supply"] <= max_supply
            )
        ]

    all_gifts = normalized + test_gifts
    all_gifts .sort(key=lambda g: g["price"], reverse=True)
    return all_gifts
