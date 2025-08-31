"""
Модуль конфигурации и профилей.

Этот модуль содержит функции для:
- Управления конфигурацией приложения.
- Создания, обновления, удаления и валидации профилей.
- Форматирования данных для отображения в меню.
- Миграции конфигурации в новый формат.

Основные функции:
- ensure_config: Гарантирует существование config.json.
- load_config: Загружает конфиг из файла.
- save_config: Сохраняет конфиг в файл.
- validate_config: Валидирует глобальный конфиг и профили.
- get_valid_config: Загружает и валидирует конфиг.
- migrate_config_if_needed: Мигрирует конфиг в новый формат.
- format_config_summary: Формирует текст для главного меню.
"""

# --- Стандартные библиотеки ---
import json
import os
import logging
from typing import Optional

# --- Сторонние библиотеки ---
import aiofiles

logger = logging.getLogger(__name__)

CURRENCY = 'XTR' # Валюта приложения
VERSION = '1.5.0' # Версия приложения
CONFIG_PATH = "config.json" # Путь к файлу конфигурации
DEV_MODE = False # Покупка тестовых подарков
MORE_LOGS = False # Логировать больше информации в консоль
MAX_PROFILES = 4 # Максимальная длина сообщения 4096 символов
PURCHASE_COOLDOWN = 0.3 # Количество покупок в секунду
USE_PROXY_BOT = False # Использовать прокси для бота
USE_PROXY_USERBOT = False # Использовать прокси для юзербота
USE_REDIS = False # Использовать Redis для кэша подарков.
REDIS_HOST = "localhost"  # Адрес Redis сервера
REDIS_PORT = 6379  # Порт Redis сервера
ALLOWED_USER_IDS = []  # Список разрешённых пользователей (Beta-версия, не рекомендуется использовать больше одного пользователя в продакшене)
DEFAULT_BOT_DELAY = 1.0  # Задержка бота по умолчанию

# Профиль для получения полного списка лимитных подарков
REQUEST_PROFILE = {
    "MIN_PRICE": 1,
    "MAX_PRICE": 10000000,
    "MIN_SUPPLY": 1,
    "MAX_SUPPLY": 100000000
}

# Список моделей устройств, системных версий и версий приложений для инициализации сессии юзербота
DEVICE_MODELS = [
    "Honor HONOR 70", "Samsung Galaxy S21", "Xiaomi Mi 11", "Google Pixel 6",
    "OnePlus 9", "Sony Xperia 5", "Huawei P50", "Nokia X20", "Motorola Edge 20", 
    "Apple iPhone 13", "Apple iPhone 14", "Apple iPhone 15"
]
SYSTEM_VERSIONS = [
    "SDK 35", "SDK 34", "SDK 33", "SDK 32", 
    "SDK 31", "SDK 30", "SDK 29", "SDK 28", 
    "SDK 27", "iOS 15.4", "iOS 16.0", "iOS 17.0"
]
APP_VERSIONS = [
    "Telegram Android 11.13.1", "Telegram Android 11.12.0", "Telegram Android 11.11.0", 
    "Telegram Android 11.10.0", "Telegram Android 11.9.0", "Telegram Android 11.8.0", 
    "Telegram Android 11.7.0", "Telegram Android 11.6.0", "Telegram Android 11.5.0", 
    "Telegram iOS 10.4.1", "Telegram iOS 10.0.0", "Telegram iOS 11.0.0"
]


def add_allowed_user(user_id: int) -> None:
    """
    Добавляет пользователя в список разрешённых.
    :param user_id: ID пользователя
    """
    ALLOWED_USER_IDS.append(user_id)
    logger.info(f"Пользователь {user_id} добавлен в список разрешённых.")


def get_allowed_users() -> list[int]:
    """
    Возвращает список разрешённых пользователей.
    :return: Список ID разрешённых пользователей
    """
    return ALLOWED_USER_IDS


def set_use_redis(value: bool) -> None:
    """
    Обновляет значение USE_REDIS в конфигурации.
    :param value: Новое значение для USE_REDIS (True или False)
    """
    global USE_REDIS
    USE_REDIS = value
    logger.info(f"Использовать Redis для кэша подарков: {USE_REDIS}")


def get_use_redis() -> bool:
    """
    Возвращает текущее значение USE_REDIS.
    :return: True, если Redis используется, иначе False
    """
    return USE_REDIS


def set_redis_config(host: str, port: int) -> None:
    """
    Устанавливает параметры подключения к Redis.
    :param host: Адрес Redis сервера
    :param port: Порт Redis сервера
    """
    global REDIS_HOST, REDIS_PORT
    REDIS_HOST = host
    REDIS_PORT = port
    logger.info(f"Настройки Redis обновлены: {REDIS_HOST}:{REDIS_PORT}")


def get_redis_config() -> tuple[str, int]:
    """
    Возвращает текущие настройки Redis.
    :return: Кортеж (REDIS_HOST, REDIS_PORT)
    """
    return REDIS_HOST, REDIS_PORT


def set_use_proxy_bot(value: bool) -> None:
    """
    Обновляет значение USE_PROXY_BOT в конфигурации.
    :param value: Новое значение для USE_PROXY_BOT (True или False)
    """
    global USE_PROXY_BOT
    USE_PROXY_BOT = value
    logger.info(f"Использовать прокси для бота: {USE_PROXY_BOT}")


def get_use_proxy_bot() -> bool:
    """
    Возвращает текущее значение USE_PROXY_BOT.
    :return: True, если прокси используется для бота, иначе False
    """
    return USE_PROXY_BOT


def set_use_proxy_userbot(value: bool) -> None:
    """
    Обновляет значение USE_PROXY_USERBOT в конфигурации.
    :param value: Новое значение для USE_PROXY_USERBOT (True или False)
    """
    global USE_PROXY_USERBOT
    USE_PROXY_USERBOT = value
    logger.info(f"Использовать прокси для юзербота: {USE_PROXY_USERBOT}")


def get_use_proxy_userbot() -> bool:
    """
    Возвращает текущее значение USE_PROXY_USERBOT.
    :return: True, если прокси используется для юзербота, иначе False
    """
    return USE_PROXY_USERBOT


def DEFAULT_PROFILE(user_id: int) -> dict:
    """
    Создаёт профиль с дефолтными настройками для указанного пользователя.
    :param user_id: ID пользователя
    :return: Словарь профиля
    """
    return {
        "NAME": None,
        "MIN_PRICE": 5000,
        "MAX_PRICE": 10000,
        "MIN_SUPPLY": 1000,
        "MAX_SUPPLY": 10000,
        "LIMIT": 1000000,
        "COUNT": 5,
        "TARGET_USER_ID": user_id,
        "TARGET_CHAT_ID": None,
        "TARGET_TYPE": None,
        "SENDER": "bot",
        "BOUGHT": 0,
        "SPENT": 0,
        "DONE": False
    }


def DEFAULT_CONFIG(user_id: int) -> dict:
    """
    Дефолтная конфигурация: глобальные поля + список профилей.
    :param user_id: ID пользователя
    :return: Словарь конфигурации
    """
    return {
        "BALANCE": 0,
        "ACTIVE": False,
        "DEPOSIT_ENBALE": False,
        "LAST_MENU_MESSAGE_ID": None,
        "PROFILES": [DEFAULT_PROFILE(user_id)],
        "USERBOT": {
            "API_ID": None,
            "API_HASH": None,
            "PHONE": None,
            "USER_ID": None,
            "USERNAME": None,
            "BALANCE": 0,
            "ENABLED": False,
            "CONFIG_ID": None,
            "UPDATE_INTERVAL": 45
        }
    }


# Типы и требования для каждого поля профиля
PROFILE_TYPES = {
    "NAME": (str, True),
    "MIN_PRICE": (int, False),
    "MAX_PRICE": (int, False),
    "MIN_SUPPLY": (int, False),
    "MAX_SUPPLY": (int, False),
    "LIMIT": (int, False),
    "COUNT": (int, False),
    "TARGET_USER_ID": (int, True),
    "TARGET_CHAT_ID": (str, True),
    "TARGET_TYPE": (str, True),
    "SENDER": (str, True),
    "BOUGHT": (int, False),
    "SPENT": (int, False),
    "DONE": (bool, False),
}


# Типы и требования для глобальных полей
CONFIG_TYPES = {
    "BALANCE": (int, False),
    "ACTIVE": (bool, False),
    "DEPOSIT_ENBALE": (bool, False),
    "LAST_MENU_MESSAGE_ID": (int, True),
    "PROFILES": (list, False),
    "USERBOT": (dict, False)
}


def is_valid_type(value: object, expected_type: type, allow_none: bool = False) -> bool:
    """
    Проверяет тип значения с учётом допуска None.
    :param value: Проверяемое значение
    :param expected_type: Ожидаемый тип
    :param allow_none: Разрешён ли None
    :return: True если тип корректен
    """
    if value is None:
        return allow_none
    return isinstance(value, expected_type)


async def ensure_config(user_id: int, path: str = CONFIG_PATH):
    """
    Гарантирует существование config.json.
    :param user_id: ID пользователя
    :param path: Путь к файлу конфигурации
    """
    if not os.path.exists(path):
        async with aiofiles.open(path, mode="w", encoding="utf-8") as f:
            await f.write(json.dumps(DEFAULT_CONFIG(user_id), indent=2))
        logger.info(f"Создана конфигурация: {path}")


async def load_config(path: str = CONFIG_PATH) -> dict:
    """
    Загружает конфиг из файла (без валидации). Гарантирует, что файл существует.
    :param path: Путь к файлу конфигурации
    :return: Словарь конфигурации
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Файл {path} не найден. Используйте ensure_config.")
    async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
        data = await f.read()
        return json.loads(data)


async def save_config(config: dict, path: str = CONFIG_PATH):
    """
    Сохраняет конфиг в файл.
    :param config: Словарь конфигурации
    :param path: Путь к файлу
    """
    async with aiofiles.open(path, mode="w", encoding="utf-8") as f:
        await f.write(json.dumps(config, indent=2))
    logger.info(f"Конфигурация сохранена.")


async def validate_profile(profile: dict, user_id: Optional[int] = None) -> dict:
    """
    Валидирует один профиль.
    :param profile: Словарь профиля
    :param user_id: ID пользователя
    :return: Валидированный профиль
    """
    valid = {}
    default = DEFAULT_PROFILE(user_id or 0)
    for key, (expected_type, allow_none) in PROFILE_TYPES.items():
        if key not in profile or not is_valid_type(profile[key], expected_type, allow_none):
            valid[key] = default[key]
        else:
            valid[key] = profile[key]
    return valid


async def validate_config(config: dict, user_id: int) -> dict:
    """
    Валидирует глобальный конфиг и все профили.
    :param config: Словарь конфигурации
    :param user_id: ID пользователя
    :return: Валидированный конфиг
    """
    valid = {}
    default = DEFAULT_CONFIG(user_id)
    # Верхний уровень
    for key, (expected_type, allow_none) in CONFIG_TYPES.items():
        if key == "PROFILES":
            profiles = config.get("PROFILES", [])
            # Валидация профилей
            valid_profiles = []
            for profile in profiles:
                valid_profiles.append(await validate_profile(profile, user_id))
            if not valid_profiles:
                valid_profiles = [DEFAULT_PROFILE(user_id)]
            valid["PROFILES"] = valid_profiles
        elif key == "USERBOT":
            userbot_data = config.get("USERBOT", {})
            default_userbot = default["USERBOT"]
            valid_userbot = {}
            for sub_key, default_value in default_userbot.items():
                value = userbot_data.get(sub_key, default_value)
                valid_userbot[sub_key] = value
            valid["USERBOT"] = valid_userbot
        else:
            if key not in config or not is_valid_type(config[key], expected_type, allow_none):
                valid[key] = default[key]
            else:
                valid[key] = config[key]
    return valid


async def get_valid_config(user_id: int, path: str = CONFIG_PATH) -> dict:
    """
    Загружает, валидирует и при необходимости обновляет config.json.
    :param user_id: ID пользователя
    :param path: Путь к файлу конфигурации
    :return: Валидированный конфиг
    """
    await ensure_config(user_id, path)
    config = await load_config(path)
    validated = await validate_config(config, user_id)
    # Если валидированная версия отличается, сохранить
    if validated != config:
        await save_config(validated, path)
    return validated


async def migrate_config_if_needed(user_id: int, path: str = CONFIG_PATH):
    """
    Проверяет и преобразует config.json из старого формата (без PROFILES)
    в новый (список профилей). Работает асинхронно.
    :param user_id: ID пользователя
    :param path: Путь к файлу конфигурации
    """
    if not os.path.exists(path):
        return

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            data = await f.read()
            config = json.loads(data)
    except Exception:
        logger.error(f"Конфиг {path} повреждён.")
        os.remove(path)
        logger.error(f"Повреждённый конфиг {path} удалён.")
        return

    # Если уже новый формат, ничего не делаем
    if "PROFILES" in config:
        return

    # Формируем профиль из старых ключей
    profile_keys = [
        "MIN_PRICE", "MAX_PRICE", "MIN_SUPPLY", "MAX_SUPPLY",
        "COUNT", "LIMIT", "TARGET_USER_ID", "TARGET_CHAT_ID",
        "BOUGHT", "SPENT", "DONE"
    ]
    profile = {}
    for key in profile_keys:
        if key in config:
            profile[key] = config[key]

    profile.setdefault("LIMIT", 1000000)
    profile.setdefault("SPENT", 0)
    profile.setdefault("BOUGHT", 0)
    profile.setdefault("DONE", False)
    profile.setdefault("COUNT", 5)

    # Собираем новый формат
    new_config = {
        "BALANCE": config.get("BALANCE", 0),
        "DEPOSIT_ENBALE": config.get("DEPOSIT_ENBALE", False),
        "ACTIVE": config.get("ACTIVE", False),
        "LAST_MENU_MESSAGE_ID": config.get("LAST_MENU_MESSAGE_ID"),
        "PROFILES": [profile],
    }

    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(new_config, ensure_ascii=False, indent=2))
    logger.info(f"Конфиг {path} мигрирован в новый формат.")


async def update_config_from_env(path: str = CONFIG_PATH, config_data: str = None):
    """
    Обновляет конфиг из переменной среды CONFIG_DATA.
    :param path: Путь к файлу конфигурации
    :param config_data: Данные конфигурации в формате JSON
    """
    try:
        config_dict = json.loads(config_data)
    except Exception as e:
        logger.error(f"CONFIG_DATA не является валидным JSON: {e}")
        return

    try:
        async with aiofiles.open(path, mode="w", encoding="utf-8") as f:
            await f.write(json.dumps(config_dict, indent=2, ensure_ascii=False))
        logger.info(f"Конфиг успешно обновлён из переменной среды CONFIG_DATA.")
    except Exception as e:
        logger.error(f"Ошибка при сохранении конфига из CONFIG_DATA: {e}")


async def get_profile(config: dict, index: int = 0) -> dict:
    """
    Получить профиль по индексу (по умолчанию первый).
    :param config: Словарь конфигурации
    :param index: Индекс профиля
    :return: Словарь профиля
    """
    profiles = config.get("PROFILES", [])
    if not profiles:
        raise ValueError("Нет профилей в конфиге")
    return profiles[index]


async def add_profile(config: dict, profile: dict, save: bool = True) -> dict:
    """
    Добавляет новый профиль в конфиг.
    :param config: Словарь конфигурации
    :param profile: Новый профиль
    :param save: Сохранять ли конфиг
    :return: Обновлённый конфиг
    """
    config.setdefault("PROFILES", []).append(profile)
    if save:
        await save_config(config)
    return config


async def update_profile(config: dict, index: int, new_profile: dict, save: bool = True) -> dict:
    """
    Обновляет профиль по индексу.
    :param config: Словарь конфигурации
    :param index: Индекс профиля
    :param new_profile: Новый профиль
    :param save: Сохранять ли конфиг
    :return: Обновлённый конфиг
    """
    if "PROFILES" not in config or index >= len(config["PROFILES"]):
        raise IndexError("Профиль не найден")
    config["PROFILES"][index] = new_profile
    if save:
        await save_config(config)
    return config


async def remove_profile(config: dict, index: int, user_id: int, save: bool = True) -> dict:
    """
    Удаляет профиль по индексу.
    :param config: Словарь конфигурации
    :param index: Индекс профиля
    :param user_id: ID пользователя
    :param save: Сохранять ли конфиг
    :return: Обновлённый конфиг
    """
    if "PROFILES" not in config or index >= len(config["PROFILES"]):
        raise IndexError("Профиль не найден")
    config["PROFILES"].pop(index)
    if not config["PROFILES"]:
        # Добавить дефолтный если удалили все
        config["PROFILES"].append(DEFAULT_PROFILE(user_id))
    if save:
        await save_config(config)
    return config


async def get_deposit_enabled() -> bool:
    """
    Возвращает статус DEPOSIT_ENBALE из config.json (True/False).
    Если конфиг отсутствует или параметр не найден — возвращает False.
    :return: True если депозит включён, иначе False
    """
    if not os.path.exists(CONFIG_PATH):
        return False
    async with aiofiles.open(CONFIG_PATH, mode="r", encoding="utf-8") as f:
        data = await f.read()
        try:
            config = json.loads(data)
        except Exception:
            return False
    return bool(config.get("DEPOSIT_ENBALE", False))


def format_config_summary(config: dict, user_id: int) -> str:
    """
    Формирует текст для главного меню: статус, баланс, и список всех профилей (каждый с кратким описанием).
    :param config: Вся конфигурация (словарь)
    :param user_id: ID пользователя для отображения "Вы"
    :return: Готовый HTML-текст для меню
    """
    status_text = "🟢 Активен" if config.get("ACTIVE") else "🔴 Неактивен"
    balance = config.get("BALANCE", 0)
    profiles = config.get("PROFILES", [])
    userbot = config.get("USERBOT", {})
    userbot_balance = userbot.get("BALANCE", 0)
    session_state = True if userbot.get("API_ID") and userbot.get("API_HASH") and userbot.get("PHONE") else False

    lines = [f"🚦 <b>Статус:</b> {status_text}"]
    for idx, profile in enumerate(profiles, 1):
        target_display = get_target_display(profile, user_id)
        sender = '<code>Бот</code>' if profile['SENDER'] == 'bot' else f'<code>Юзербот</code>'
        profile_name = f'Профиль {idx}' if  not profile['NAME'] else profile['NAME']
        state_profile = (
            " ✅ <b>(завершён)</b>" if profile.get('DONE')
            else " ⚠️ <b>(частично)</b>" if profile.get('SPENT', 0) > 0
            else ""
        )
        userbot_state_profile = ' 🔕' if profile['SENDER'] == 'userbot' and (not session_state or userbot.get('ENABLED') == False) else ''
        line = (
            "\n"
            f"┌🏷️ <b>{profile_name}</b>{userbot_state_profile}{state_profile}\n"
            f"├💰 <b>Цена</b>: {profile.get('MIN_PRICE'):,} – {profile.get('MAX_PRICE'):,} ★\n"
            f"├📦 <b>Саплай</b>: {profile.get('MIN_SUPPLY'):,} – {profile.get('MAX_SUPPLY'):,}\n"
            f"├🎁 <b>Куплено</b>: {profile.get('BOUGHT'):,} / {profile.get('COUNT'):,}\n"
            f"├⭐️ <b>Лимит</b>: {profile.get('SPENT'):,} / {profile.get('LIMIT'):,} ★\n"
            f"├👤 <b>Получатель</b>: {target_display}\n"
            f"└📤 <b>Отправитель</b>: {sender}"
        )
        lines.append(line)

    # Баланс основного бота
    lines.append(f"\n💰 <b>Баланс бота</b>: {balance:,} ★")

    # Добавляем баланс userbot, если сессия активна
    if session_state:
        lines.append(
            f"💰 <b>Баланс юзербота</b>: {userbot_balance:,} ★"
            f"{' 🔕' if not userbot.get('ENABLED') else ''}"
        )
    else:
        lines.append(
            f"💰 <b>Баланс юзербота</b>: Не подключён!"
        )

    return "\n".join(lines)


def get_target_display(profile: dict, user_id: int) -> str:
    """
    Возвращает строковое описание получателя подарка для профиля.
    :param profile: словарь профиля
    :param user_id: id текущего пользователя
    :return: строка для меню
    """
    target_chat_id = profile.get("TARGET_CHAT_ID")
    target_user_id = profile.get("TARGET_USER_ID")
    target_type = profile.get("TARGET_TYPE")
    if target_chat_id:
        if target_type == "channel":
            return f"{target_chat_id} (Канал)"
        else:
            return f"{target_chat_id}"
    elif str(target_user_id) == str(user_id):
        return f"<code>{target_user_id}</code> (Вы)"
    else:
        return f"<code>{target_user_id}</code>"
    

def get_target_display_local(target_user_id: int, target_chat_id: str, user_id: int) -> str:
    """
    Возвращает строковое описание получателя подарка на основе выбранного получателя и user_id.
    Если оба параметра равны None, возвращает пустую строку.
    :param target_user_id: ID пользователя
    :param target_chat_id: ID чата
    :param user_id: ID текущего пользователя
    :return: строка для меню
    """
    if target_chat_id:
        return f"{target_chat_id}"
    elif str(target_user_id) == str(user_id):
        return f"<code>{target_user_id}</code> (Вы)"
    else:
        return f"<code>{target_user_id}</code>"
