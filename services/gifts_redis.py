"""
Модуль работы с подарками через Redis.

Этот модуль содержит функции для:
- Подключения к Redis и получения данных.
- Нормализации объектов подарков в словари.
- Получения и фильтрации списка подарков из Redis.
- Генерации тестовых подарков для отладки.

Основные функции:
- get_redis: Возвращает глобальный экземпляр клиента Redis.
- normalize_gift: Преобразует объект Gift (словарь) в словарь с основными характеристиками.
- get_redis_filtered_gifts: Получает и фильтрует список подарков из Redis.
"""

# --- Стандартные библиотеки ---
import json
import logging
import asyncio

# --- Сторонние библиотеки ---
import redis.asyncio as redis

# --- Внутренние модули ---
from utils.mockdata import generate_test_gifts
from services.config import DEV_MODE, MORE_LOGS, get_redis_config


logger = logging.getLogger(__name__)

r = None # Глобальный клиент Redis (создаётся один раз на импорт)

def get_redis():
    """
    Возвращает глобальный экземпляр клиента Redis.
    Создаёт подключение при первом вызове.
    :return: Экземпляр redis.Redis
    """
    redis_host, redis_port = get_redis_config()
    global r
    if r is None:
        try:
            r = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True,
                socket_timeout=1,
                socket_connect_timeout=1
            )
        except Exception as e:
            logger.error(f"Ошибка подключения к Redis: {e}")
            r = None
    return r

async def is_redis_active():
    """
    Проверяет, справляется ли Redis с задачей обновления списка подарков.

    :return: Кортеж (список подарков из Redis, состояние Redis)
    """
    try:
        gifts_redis, state_redis = await get_redis_filtered_gifts(
            1,
            10000000,
            1,
            100000000
        )
        if state_redis:
            if MORE_LOGS:
                logger.info(f"Redis активно используется для обновления списка подарков. Найдено подарков: {len(gifts_redis)}")
            return gifts_redis, state_redis
    except Exception as e:
        logger.error(f"Ошибка проверки состояния Redis: {e}")
    return [], False

def normalize_gift(gift: dict) -> dict:
    """
    Преобразует объект Gift (словарь) в словарь с основными характеристиками подарка.

    :param gift: Словарь Gift.
    :return: Словарь с параметрами подарка.
    """
    return {
        "id": gift.get("id"),
        "price": gift.get("price"),
        "supply": gift.get("supply", 0),
        "left": gift.get("remaining_count", 0),
        "sticker_file_id": gift.get("sticker_file_id", None),
        "emoji": gift.get("emoji", None)
    }

async def get_redis_filtered_gifts(
    min_price: int,
    max_price: int,
    min_supply: int,
    max_supply: int,
    unlimited: bool = False,
    add_test_gifts: bool = False,
    test_gifts_count: int = 5
) -> list[dict]:
    """
    Получает и фильтрует список подарков из Redis, возвращает их в нормализованном виде.

    :param min_price: Минимальная цена подарка.
    :param max_price: Максимальная цена подарка.
    :param min_supply: Минимальный supply подарка.
    :param max_supply: Максимальный supply подарка.
    :param unlimited: Если True — игнорировать supply при фильтрации.
    :param add_test_gifts: Добавлять тестовые подарки в конец списка.
    :param test_gifts_count: Количество тестовых подарков.
    :return: Список словарей с параметрами подарков, отсортированный по цене по убыванию.
    """
    try:
        # Получаем, нормализуем и фильтруем подарки из redis потока
        r = get_redis()
        data = await asyncio.wait_for(r.get("market:gifts"), timeout=1.0)
        if not data:
            return [], False # Возвращаем пустой список и False, если данных нет
        gifts = json.loads(data)
        if MORE_LOGS: 
            logger.info(f"Получено {len(gifts)} подарков из Redis.")

        filtered = []
        for gift in gifts:
            price_ok = min_price <= gift["price"] <= max_price
            # Логика по unlimited
            if unlimited:
                supply_ok = True
            else:
                supply = gift.get("supply") or 0
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
        all_gifts.sort(key=lambda g: g["price"], reverse=True)
        return all_gifts, True  # Возвращаем True, чтобы показать, что данные получены из Redis
    except Exception as e:
        if MORE_LOGS:
            logger.error(f"Ошибка при получении данных из Redis: {e}")
        return [], False  # Возвращаем пустой список и False, если Redis недоступен