"""
Модуль управления подарками.

Этот модуль содержит функции для работы с подарками, включая:
- Обновление кеша подарков от userbot.
- Проверку актуальности кеша userbot.
- Фильтрацию подарков по параметрам профиля.
- Получение списка подарков из различных источников (Redis, bot, userbot).

Основные функции:
- userbot_gifts_updater: Фоновая задача для обновления кеша подарков от userbot.
- is_userbot_cache_fresh: Проверяет, актуален ли кеш userbot.
- filter_gifts_by_profile: Фильтрует список подарков по параметрам профиля.
- get_best_gift_list: Возвращает наиболее полный список подарков из доступных источников.
"""

# --- Стандартные библиотеки ---
import time
import random
import asyncio
import logging

# --- Сторонние библиотеки ---
from aiogram import Bot

# --- Внутренние модули ---
from services.config import get_valid_config, get_use_redis, MORE_LOGS
from services.gifts_bot import get_bot_filtered_gifts
from services.gifts_userbot import get_userbot_filtered_gifts
from services.gifts_redis import get_redis_filtered_gifts, is_redis_active


logger = logging.getLogger(__name__)

userbot_all_gifts: list[dict] = [] # Глобальный список подарков от userbot
last_update_userbot: float = 0 # Время последнего обновления кеша userbot

async def userbot_gifts_updater(user_id: int, base_interval: int = 45) -> None:
    """
    Запускает фоновую задачу для регулярного обновления кеша подарков от юзербота.

    :param user_id: Telegram ID владельца userbot-сессии
    :param base_interval: Минимальный интервал обновления (в секундах); 
                          фактическая пауза будет от base_interval до base_interval + 10
    :return: None
    """
    global userbot_all_gifts, last_update_userbot
    
    while True:
        config = await get_valid_config(user_id)
        userbot_config = config.get("USERBOT", {})
        base_interval = userbot_config["UPDATE_INTERVAL"]
        use_redis = get_use_redis()

        # Проверяем, если Redis активен и справляется с задачей обновления списка подарков
        if use_redis:
            _, state_redis = await is_redis_active()
            if state_redis:
                delay = random.randint(base_interval, base_interval + 10)
                await asyncio.sleep(delay)
                continue  # Если Redis активен, не запрашиваем userbot
        try:
            userbot_all_gifts = await get_userbot_filtered_gifts(
                user_id,
                min_price=1,
                max_price=10000000,
                min_supply=1,
                max_supply=100000000,
                unlimited=False
            )
            last_update_userbot = time.time()
        except Exception as e:
            logger.error(f"Ошибка в userbot_gifts_updater: {e}")
            
        delay = random.randint(base_interval, base_interval + 10)
        if MORE_LOGS:
            logger.info(f"Обновление подарков от userbot через {delay} секунд...")
        await asyncio.sleep(delay)


def is_userbot_cache_fresh(max_age: int = 55) -> bool:
    """
    Проверяет, актуален ли кеш userbot.

    :param max_age: Максимальное допустимое время с последнего обновления (в секундах)
    :return: True, если кеш свежий
    """
    return time.time() - last_update_userbot < max_age


def filter_gifts_by_profile(gifts: list[dict], profile: dict) -> list[dict]:
    """
    Фильтрует список подарков по параметрам конкретного профиля.

    :param gifts: Список всех доступных подарков (словари)
    :param profile: Словарь с параметрами профиля (ценовой диапазон, лимиты)
    :return: Отфильтрованный список подарков, подходящих под профиль
    """
    return [
        g for g in gifts
        if profile["MIN_PRICE"] <= g.get("price", 0) <= profile["MAX_PRICE"]
        and profile["MIN_SUPPLY"] <= g.get("supply", 0) <= profile["MAX_SUPPLY"]
    ]


async def get_best_gift_list(user_id: int, bot: Bot, profile: dict) -> list[dict]:
    """
    Возвращает наиболее полный список подарков — либо от Redis, либо от бота, либо от userbot,
    в зависимости от того, где подарков больше, при условии фильтрации под профиль.

    :param bot: Объект aiogram-бота
    :param profile: Словарь с параметрами профиля (фильтрация по цене, количеству и т.д.)
    :return: Отфильтрованный список подарков (в виде list[dict])
    """
    global userbot_all_gifts
    config = await get_valid_config(user_id)
    userbot_config = config.get("USERBOT", {})
    base_interval = userbot_config["UPDATE_INTERVAL"]
    use_redis = get_use_redis()

    gifts_redis = []
    try:
        if use_redis:
            gifts_redis, state_redis = await get_redis_filtered_gifts(
                profile["MIN_PRICE"],
                profile["MAX_PRICE"],
                profile["MIN_SUPPLY"],
                profile["MAX_SUPPLY"]
            )
            if state_redis: # Если данные получены из Redis
                return gifts_redis
    except Exception as e:
        logger.error(f"Ошибка получения списка подарков из Redis: {e}")

    try:
        gifts_bot = await get_bot_filtered_gifts(
            bot,
            profile["MIN_PRICE"],
            profile["MAX_PRICE"],
            profile["MIN_SUPPLY"],
            profile["MAX_SUPPLY"]
        )
    except Exception as e:
        logger.error(f"Ошибка получения списка подарков от бота: {e}")
        gifts_bot = []

    gifts_userbot = filter_gifts_by_profile(userbot_all_gifts, profile)

    if is_userbot_cache_fresh(base_interval + 10) and len(gifts_userbot) > len(gifts_bot):
        return gifts_userbot

    return gifts_bot
