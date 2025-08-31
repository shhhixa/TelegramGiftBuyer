"""
Модуль покупки подарков через Pyrogram userbot.

Этот модуль содержит функции для:
- Покупки подарков через userbot.
- Обработки ошибок и повторных попыток при покупке.
- Тестирования покупки подарков в режиме разработки.

Основные функции:
- buy_gift_userbot: Покупает подарок через Pyrogram userbot.
"""

# --- Стандартные библиотеки ---
import asyncio
import logging
import random

# --- Внутренние модули ---
from services.config import get_valid_config, save_config, DEV_MODE
from services.balance import change_balance_userbot
from services.userbot import get_userbot_client

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import (
    FloodWait,
    BadRequest,
    Forbidden,
    RPCError,
    AuthKeyUnregistered
)

logger = logging.getLogger(__name__)

async def buy_gift_userbot(
    session_user_id: int,
    gift_id: int,
    target_user_id: int | None,
    target_chat_id: str | None,
    gift_price: int,
    file_id: str | None = None,
    retries: int = 3,
    add_test_purchases: bool = False
) -> bool:
    """
    Покупает подарок через Pyrogram userbot.

    :param session_user_id: ID сессии юзербота
    :param gift_id: ID подарка
    :param target_user_id: ID получателя-пользователя (или None)
    :param target_chat_id: ID получателя-чата (или None)
    :param gift_price: Стоимость подарка в звёздах
    :param file_id: Не используется (зарезервировано)
    :param retries: Количество попыток
    :param add_test_purchases: Включает случайные покупки в режиме разработки
    :return: True, если покупка успешна
    """
    if add_test_purchases or DEV_MODE:
        result = random.choice([True, True, True, False])
        logger.info(f"[ТЕСТ] ({result}) Покупка подарка {gift_id} за {gift_price} (userbot, имитация)")
        return result

    config = await get_valid_config(session_user_id)
    userbot_config = config.get("USERBOT", {})
    userbot_balance = userbot_config.get("BALANCE", 0)

    if userbot_balance < gift_price:
        logger.error(f"Недостаточно звёзд для покупки подарка {gift_id} (требуется: {gift_price}, доступно: {userbot_balance})")
        
        config = await get_valid_config(session_user_id)
        config["USERBOT"]["ENABLED"] = False
        await save_config(config)

        return False

    client: Client = await get_userbot_client(session_user_id)
    if client is None:
        logger.error("Не удалось получить объект клиента userbot.")
        return False

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Попытка {attempt}/{retries} покупки подарка юзерботом...")

            if target_user_id and not target_chat_id:
                result_send: Message = await client.send_gift(gift_id=int(gift_id), 
                                                         chat_id=int(target_user_id), 
                                                         is_private=True)
            elif target_chat_id and not target_user_id:
                result_send: Message = await client.send_gift(gift_id=int(gift_id), 
                                                         chat_id=target_chat_id, 
                                                         is_private=True)
            else:
                logger.warning("Указаны оба параметра — target_user_id и target_chat_id. Прерываем.")
                break

            new_balance = await change_balance_userbot(-gift_price)
            logger.info(f"Успешная покупка подарка {gift_id} за {gift_price} звёзд. Остаток: {new_balance}")
            return True
        
        except FloodWait as e:
            logger.error(f"Flood wait: ждём {e.value} секунд")
            await asyncio.sleep(e.value)

        except BadRequest as e:
            if "BALANCE_TOO_LOW" in str(e) or "not enough" in str(e).lower():
                logger.error(f"Недостаточно звёзд: {e}")
                return False
            logger.error(f"(BadRequest) Критическая ошибка: {e}")
            return False

        except Forbidden as e:
            logger.error(f"(Forbidden) Критическая ошибка: {e}")
            return False
        
        except AuthKeyUnregistered as e:
            logger.error(f"(AuthKeyUnregistered) Критическая ошибка: {e}")
            return False

        except RPCError as e:
            logger.error(f"RPC ошибка: {e}")
            await asyncio.sleep(2 ** attempt)

        except Exception as e:
            delay = 2 ** attempt
            logger.error(f"[{attempt}/{retries}] Ошибка userbot при покупке: {e}. Повтор через {delay} сек...")
            await asyncio.sleep(delay)

    logger.error(f"Не удалось купить подарок {gift_id} после {retries} попыток.")
    return False
