"""
Модуль для работы с прокси-соединениями.

Этот модуль содержит функции для:
- Получения данных прокси для пользователя.
- Создания aiohttp-сессии с прокси.
- Формирования настроек прокси для юзербота.

Основные функции:
- get_proxy_data: Возвращает данные для прокси-соединения.
- get_aiohttp_session: Создаёт aiohttp-сессию с прокси.
- get_userbot_proxy: Формирует настройки прокси для юзербота.
"""

# --- Стандартные библиотеки ---
import logging

# --- Сторонние библиотеки ---
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

# --- Внутренние модули ---
from services.config import set_use_proxy_bot, set_use_proxy_userbot, MORE_LOGS
from utils.env_loader import get_env_variable


load_dotenv(override=False)
logger = logging.getLogger(__name__)

async def get_proxy_data(user_id: int, bot_id: int) -> dict | None:
    """
    Возвращает данные для прокси-соединения для указанного пользователя.

    :param user_id: Telegram ID пользователя, для которого запрашиваются настройки прокси.
    :param bot_id: ID бота, если требуется специфическая конфигурация для бота.
    :return: Словарь с полями 'hostname', 'port', 'username', 'password' или None, если прокси не используется.
    """
    if MORE_LOGS:
        logger.info(f"Получаем proxy данные для user_id: {user_id}, bot_id: {bot_id}")
    
    env_proxy_hostname = get_env_variable("PROXY_HOSTNAME", None)
    env_proxy_port = get_env_variable("PROXY_PORT", None)
    env_proxy_username = get_env_variable("PROXY_USERNAME", None)
    env_proxy_password = get_env_variable("PROXY_PASSWORD", None)

    proxy = {
        "hostname": env_proxy_hostname,
        "port": int(env_proxy_port) if env_proxy_port else None,
        "username": env_proxy_username,
        "password": env_proxy_password
    }

    # Проверяем, если данные прокси пустые, возвращаем None
    if not proxy.get("hostname") or not proxy.get("port"):
        return None

    return proxy

async def get_aiohttp_session(user_id: int) -> AiohttpSession | None:
    """
    Создаёт aiohttp-сессию с прокси для указанного пользователя.

    :param user_id: Telegram ID пользователя.
    :return: Экземпляр AiohttpSession с прокси или None, если прокси не используется.
    """
    # Проверяем состояние использования прокси для бота
    # Проверяем наличие параметра USE_PROXY_BOT
    use_proxy_bot = None
    env_use_proxy_bot = get_env_variable("USE_PROXY_BOT", None)
    if env_use_proxy_bot is not None:
        use_proxy_bot = env_use_proxy_bot.lower() == "true"
        set_use_proxy_bot(use_proxy_bot)

    # Проверяем, если прокси не используется
    if not use_proxy_bot:
        if MORE_LOGS: logger.info("Прерываем выполнение функции get_aiohttp_session")
        return None
    
    data_proxy = await get_proxy_data(user_id, None)
    if not data_proxy: 
        if MORE_LOGS: logger.info("Прерываем выполнение функции get_aiohttp_session")
        return None
    else:
        logger.info(f"Используем прокси для бота: {data_proxy['hostname'][:5]}...:{str(data_proxy['port'])[:5]}...")

    proxy_url = f"socks5://{data_proxy.get('username')}:{data_proxy.get('password')}@{data_proxy.get('hostname')}:{data_proxy.get('port')}"

    if proxy_url:
        return AiohttpSession(proxy=proxy_url)
    else:
        if MORE_LOGS: logger.info("Прерываем выполнение функции get_aiohttp_session")
        return None
    
async def get_userbot_proxy(user_id: int, bot_id: int) -> dict | None:
    """
    Формирует словарь настроек прокси для подключения юзербота.

    :param user_id: Telegram ID пользователя.
    :param bot_id: ID бота, если требуется специфическая конфигурация для бота.
    :return: Словарь настроек прокси или None, если прокси не используется.
    """
    # Проверяем состояние использования прокси для юзербота
    # Проверяем наличие параметра USE_PROXY_USERBOT
    use_proxy_userbot = None
    env_use_proxy_userbot = get_env_variable("USE_PROXY_USERBOT", None)
    if env_use_proxy_userbot is not None:
        use_proxy_userbot = env_use_proxy_userbot.lower() == "true"
        set_use_proxy_userbot(use_proxy_userbot)

    # Проверяем, если прокси не используется
    if not use_proxy_userbot:
        if MORE_LOGS: logger.info("Прерываем выполнение функции get_userbot_proxy")
        return None
    
    data_proxy = await get_proxy_data(user_id, bot_id)
    if not data_proxy: 
        if MORE_LOGS: logger.info("Прерываем выполнение функции get_userbot_proxy")
        return None
    else:
        logger.info(f"Используем прокси для юзербота: hostname: {data_proxy['hostname'][:4]}..{data_proxy['hostname'][-4:]}, port: {str(data_proxy['port'])[:2]}..{str(data_proxy['port'])[-2:]}")

    settings = {
        "scheme": "socks5",
        "hostname": data_proxy.get("hostname"),
        "port": data_proxy.get("port"),
        "username": data_proxy.get("username"),
        "password": data_proxy.get("password")
    }

    return settings