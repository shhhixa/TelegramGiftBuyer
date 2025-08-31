"""
Модуль для загрузки переменных окружения.

Этот модуль проверяет наличие файла .env и загружает переменные окружения из него, если файл существует.
Если файл .env отсутствует, переменные загружаются из системных переменных окружения.

Основные функции:
- get_env_variable: Получает значение переменной окружения с возможностью указания значения по умолчанию.
"""

# --- Стандартные библиотеки ---
import os
import logging

# --- Сторонние библиотеки ---
from dotenv import load_dotenv
from utils.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

# >> Список возможных переменных окружения:
# TELEGRAM_BOT_TOKEN: str  # Токен Telegram-бота
# TELEGRAM_USER_ID: int    # ID пользователя Telegram
# USE_REDIS: bool          # Использовать Redis для кэша (True/False)
# REDIS_HOST: str          # Хост Redis
# REDIS_PORT: int          # Порт Redis
# USE_PROXY_BOT: bool      # Использовать прокси для бота (True/False)
# USE_PROXY_USERBOT: bool  # Использовать прокси для userbot (True/False)
# PROXY_HOSTNAME: str      # Хост прокси
# PROXY_PORT: int          # Порт прокси
# PROXY_USERNAME: str      # Имя пользователя для авторизации в прокси
# PROXY_PASSWORD: str      # Пароль для авторизации в прокси
# CONFIG_DATA: str         # JSON-строка с конфигурацией

# Проверяем наличие файла .env и загружаем переменные, если файл существует
if os.path.exists(".env"):
    load_dotenv(override=False)
    logger.info("Загружены переменные окружения из .env")
else:
    logger.warning("Файл .env не найден, используем os.environ.get")

def get_env_variable(key: str, default=None):
    """
    Получает значение переменной окружения.
    Если переменная не найдена, возвращает значение по умолчанию.

    :param key: Название переменной окружения
    :param default: Значение по умолчанию, если переменная не найдена
    :return: Значение переменной окружения или default
    """
    return os.getenv(key) or os.environ.get(key, default)