"""
Главный модуль приложения Telegram Gifts Bot.

Этот модуль содержит функции для:
- Запуска асинхронного приложения.
- Настройки и проверки конфигурации.
- Регистрации хендлеров и middleware.
- Запуска фоновых задач.

Основные функции:
- main: Асинхронная точка входа в приложение.
- gift_purchase_worker: Фоновый воркер для покупки подарков.

Автор: @leozizu
Канал: @pepeksey
Лицензия: MIT
"""

# --- Стандартные библиотеки ---
import asyncio
import logging
import sys

# --- Сторонние библиотеки ---
from aiogram import Bot, Dispatcher
from aiogram.utils.backoff import BackoffConfig
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from pyrogram.errors import SecurityCheckMismatch

# --- Внутренние модули ---
from services.config import (
    ensure_config,
    save_config,
    get_valid_config,
    get_target_display,
    migrate_config_if_needed,
    add_allowed_user,
    set_use_redis,
    set_redis_config,
    update_config_from_env,
    VERSION,
    PURCHASE_COOLDOWN,
    MORE_LOGS,
    DEFAULT_BOT_DELAY,
    REQUEST_PROFILE
)
from services.menu import update_menu
from services.balance import refresh_balance
from services.gifts_manager import get_best_gift_list, userbot_gifts_updater, filter_gifts_by_profile
from services.buy_bot import buy_gift
from services.buy_userbot import buy_gift_userbot
from services.userbot import try_start_userbot_from_config
from handlers.handlers_wizard import register_wizard_handlers
from handlers.handlers_catalog import register_catalog_handlers
from handlers.handlers_main import register_main_handlers
from utils.logging import setup_logging
from utils.proxy import get_aiohttp_session
from utils.env_loader import get_env_variable
from utils.log_cache import LOG_CACHE_HANDLER
from middlewares.access_control import AccessControlMiddleware
from middlewares.rate_limit import RateLimitMiddleware

setup_logging()
logger = logging.getLogger(__name__)
logging.getLogger().addHandler(LOG_CACHE_HANDLER)

TOKEN = get_env_variable("TELEGRAM_BOT_TOKEN")
USER_ID = int(get_env_variable("TELEGRAM_USER_ID", 0))
ALLOWED_USER_IDS = []
ALLOWED_USER_IDS.append(USER_ID)
add_allowed_user(USER_ID)

async def gift_purchase_worker(bot: Bot) -> None:
    """
    Фоновый воркер для покупки подарков по профилям.
    Теперь учитывает параметр LIMIT — максимальную сумму звёзд, которую можно потратить на профиль.
    Если лимит исчерпан — профиль считается завершённым и воркер переходит к следующему.

    :param bot: Экземпляр бота aiogram
    :return: None
    """
    await refresh_balance(bot)
    while True:
        try:
            config = await get_valid_config(USER_ID)

            if not config["ACTIVE"]:
                await asyncio.sleep(1)
                continue

            message = None
            report_message_lines = []
            progress_made = False  # Был ли прогресс по профилям на этом проходе
            any_success = True

            # Получаем полный список лимитных подарков
            all_gifts = await get_best_gift_list(USER_ID, bot, REQUEST_PROFILE)

            for profile_index, profile in enumerate(config["PROFILES"]):
                # Пропускаем завершённые профили
                if profile.get("DONE"):
                    continue
                # Пропускаем профили с выключенным юзерботом
                sender = profile.get("SENDER", "bot")
                if sender == "userbot":
                    userbot_config = config.get("USERBOT", {})
                    if not userbot_config.get("ENABLED", False):
                        continue

                COUNT = profile["COUNT"]
                LIMIT = profile.get("LIMIT", 0)
                TARGET_USER_ID = profile["TARGET_USER_ID"]
                TARGET_CHAT_ID = profile["TARGET_CHAT_ID"]

                # Фильтруем полный список подарков под текущий профиль
                filtered_gifts = filter_gifts_by_profile(all_gifts, profile)
                if MORE_LOGS:
                    logger.info(f"Доступно подарков после фильтрации в профиле {profile_index}: {len(filtered_gifts)}")

                if not filtered_gifts:
                    continue

                purchases = []
                before_bought = profile["BOUGHT"]
                before_spent = profile["SPENT"]

                for gift in filtered_gifts:
                    gift_id = gift["id"]
                    gift_price = gift["price"]
                    gift_total_count = gift["supply"]
                    sticker_file_id = gift["sticker_file_id"]

                    # Проверяем лимит перед каждой покупкой
                    while (profile["BOUGHT"] < COUNT and
                           profile["SPENT"] + gift_price <= LIMIT):

                        sender = profile.get("SENDER", "bot")
                        if sender == "bot":
                            success = await buy_gift(
                                bot=bot,
                                env_user_id=USER_ID,
                                gift_id=gift_id,
                                target_user_id=TARGET_USER_ID,
                                target_chat_id=TARGET_CHAT_ID,
                                gift_price=gift_price,
                                file_id=sticker_file_id
                            )
                        elif sender == "userbot":
                            userbot_config = config.get("USERBOT", {})
                            success = await buy_gift_userbot(
                                session_user_id=USER_ID,
                                gift_id=gift_id,
                                target_user_id=TARGET_USER_ID,
                                target_chat_id=TARGET_CHAT_ID,
                                gift_price=gift_price,
                                file_id=sticker_file_id
                            )
                        else:
                            logger.warning(f"Неизвестный отправитель SENDER={sender} в профиле {profile_index}")
                            success = False

                        if not success:
                            any_success = False
                            break  # Не удалось купить — пробуем следующий подарок

                        config = await get_valid_config(USER_ID)
                        profile = config["PROFILES"][profile_index]
                        profile["BOUGHT"] += 1
                        profile["SPENT"] += gift_price
                        purchases.append({"id": gift_id, "price": gift_price})
                        await save_config(config)
                        await asyncio.sleep(PURCHASE_COOLDOWN)

                        # Проверяем: не достигли ли лимит после покупки
                        if profile["SPENT"] >= LIMIT:
                            break

                    if profile["BOUGHT"] >= COUNT or profile["SPENT"] >= LIMIT:
                        break  # Достигли лимит либо по количеству, либо по сумме

                after_bought = profile["BOUGHT"]
                after_spent = profile["SPENT"]
                made_local_progress = (after_bought > before_bought) or (after_spent > before_spent)

                # Профиль полностью выполнен: либо по количеству, либо по лимиту
                if (profile["BOUGHT"] >= COUNT or profile["SPENT"] >= LIMIT) and not profile["DONE"]:
                    config = await get_valid_config(USER_ID)
                    profile = config["PROFILES"][profile_index]
                    profile["DONE"] = True
                    await save_config(config)

                    target_display = get_target_display(profile, USER_ID)
                    summary_lines = [
                        f"\n┌✅ <b>Профиль {profile_index+1}</b>\n"
                        f"├👤 <b>Получатель:</b> {target_display}\n"
                        f"├💸 <b>Потрачено:</b> {profile['SPENT']:,} / {LIMIT:,} ★\n"
                        f"└🎁 <b>Куплено </b>{profile['BOUGHT']} из {COUNT}:"
                    ]
                    gift_summary = {}
                    for p in purchases:
                        key = p["id"]
                        if key not in gift_summary:
                            gift_summary[key] = {"price": p["price"], "count": 0}
                        gift_summary[key]["count"] += 1

                    gift_items = list(gift_summary.items())
                    for idx, (gid, data) in enumerate(gift_items):
                        prefix = "   └" if idx == len(gift_items) - 1 else "   ├"
                        summary_lines.append(
                            f"{prefix} {data['price']:,} ★ × {data['count']}"
                        )
                    report_message_lines += summary_lines

                    logger.info(f"Профиль #{profile_index+1} завершён")
                    progress_made = True
                    await refresh_balance(bot)
                    continue  # К следующему профилю

                # Если ничего не куплено — баланс/лимит/подарки кончились
                if (profile["BOUGHT"] < COUNT or profile["SPENT"] < LIMIT) and not profile["DONE"] and made_local_progress:
                    target_display = get_target_display(profile, USER_ID)
                    summary_lines = [
                        f"\n┌⚠️ <b>Профиль {profile_index+1}</b> (частично)\n"
                        f"├👤 <b>Получатель:</b> {target_display}\n"
                        f"├💸 <b>Потрачено:</b> {profile['SPENT']:,} / {LIMIT:,} ★\n"
                        f"└🎁 <b>Куплено </b>{profile['BOUGHT']} из {COUNT}:"
                    ]
                    gift_summary = {}
                    for p in purchases:
                        key = p["id"]
                        if key not in gift_summary:
                            gift_summary[key] = {"price": p["price"], "count": 0}
                        gift_summary[key]["count"] += 1

                    gift_items = list(gift_summary.items())
                    for idx, (gid, data) in enumerate(gift_items):
                        prefix = "   └" if idx == len(gift_items) - 1 else "   ├"
                        summary_lines.append(
                            f"{prefix} {data['price']:,} ★ × {data['count']}"
                        )
                    report_message_lines += summary_lines

                    logger.warning(f"Профиль #{profile_index+1} не завершён")
                    progress_made = True
                    await refresh_balance(bot)
                    continue  # К следующему профилю

            if not any_success and not progress_made:
                logger.warning(
                    f"Не удалось купить ни один подарок ни в одном профиле (все попытки buy_gift были неудачны)"
                )
                config["ACTIVE"] = False
                await save_config(config)
                text = ("⚠️ Найдены подходящие подарки, но <b>не удалось</b> купить.\n"
                        "💰 Пополните баланс! Проверьте адрес получателя!\n"
                        "🪜 Проверьте типы принимаемых подарков у получателя!\n"
                        "🚦 Статус изменён на 🔴 (неактивен).")
                message = await bot.send_message(chat_id=USER_ID, text=text)
                await update_menu(
                    bot=bot, chat_id=USER_ID, user_id=USER_ID, message_id=message.message_id
                )            

            # После обработки всех профилей:
            if progress_made:
                config["ACTIVE"] = not all(p.get("DONE") for p in config["PROFILES"])
                await save_config(config)
                logger.info("Отчёт: хотя бы один профиль обработан, отправляем сводку.")
                text = "🍀 <b>Отчёт по профилям:</b>\n"
                text += "\n".join(report_message_lines) if report_message_lines else "⚠️ Покупок не совершено."
                message = await bot.send_message(chat_id=USER_ID, text=text)
                await update_menu(
                    bot=bot, chat_id=USER_ID, user_id=USER_ID, message_id=message.message_id
                )

            if all(p.get("DONE") for p in config["PROFILES"]) and config["ACTIVE"]:
                config["ACTIVE"] = False
                await save_config(config)
                text = "✅ Все профили <b>завершены</b>!\n⚠️ Нажмите ♻️ <b>Сбросить</b> или ✏️ <b>Изменить</b>!"
                message = await bot.send_message(chat_id=USER_ID, text=text)
                await update_menu(
                    bot=bot, chat_id=USER_ID, user_id=USER_ID, message_id=message.message_id
                )

        except Exception as e:
            logger.error(f"Ошибка в gift_purchase_worker: {e}")

        await asyncio.sleep(DEFAULT_BOT_DELAY)


async def main() -> None:
    """
    Асинхронная точка входа в приложение.

    - Мигрирует и проверяет конфигурационный файл (config.json)
    - Создаёт HTTP-сессию и объект бота
    - Подключает middleware (ограничения и доступ)
    - Регистрирует хендлеры
    - Запускает userbot (если он настроен)
    - Запускает фоновые задачи (покупки, обновление кеша подарков)
    - Запускает polling через aiogram Dispatcher

    :return: None
    """
    logger.info("Бот запущен. Начинаем инициализацию...")

    # Проверяем наличие параметра CONFIG_DATA
    env_config_data = get_env_variable("CONFIG_DATA", None)
    if env_config_data is not None:
        await update_config_from_env(config_data=env_config_data)

    # Проверяем и мигрируем конфигурацию
    await migrate_config_if_needed(USER_ID)
    await ensure_config(USER_ID)

    # Проверяем Redis, если указано в переменных окружения
    env_use_redis = get_env_variable("USE_REDIS", None)
    if env_use_redis is not None:
        use_redis = env_use_redis.lower() == "true"
        set_use_redis(use_redis)

    # Настройка Redis, если указано в переменных окружения
    redis_host = get_env_variable("REDIS_HOST", "localhost")
    redis_port = int(get_env_variable("REDIS_PORT", 6379))
    set_redis_config(redis_host, redis_port)

    session = await get_aiohttp_session(USER_ID)
    bot = Bot(token=TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(RateLimitMiddleware(
        commands_limits={"/start": 10, "/withdraw_all": 10, "/refund": 10}, 
        allowed_user_ids=ALLOWED_USER_IDS
    ))
    dp.callback_query.middleware(RateLimitMiddleware(
        commands_limits={"guest_deposit_menu": 10},
        allowed_user_ids=ALLOWED_USER_IDS
    ))
    dp.message.middleware(AccessControlMiddleware(ALLOWED_USER_IDS))
    dp.callback_query.middleware(AccessControlMiddleware(ALLOWED_USER_IDS))

    # Простая защита: отключение громоздких traceback'ов SecurityCheckMismatch
    def _loop_exception_handler(loop, context):
        exc = context.get("exception")
        if isinstance(exc, SecurityCheckMismatch):
            logger.warning("Pyrogram SecurityCheckMismatch — подробный traceback отключён.")
            return
        loop.default_exception_handler(context)

    try:
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(_loop_exception_handler)
    except RuntimeError:
        logger.info("Нет запущенного event loop для установки обработчика исключений.")

    logging.getLogger("pyrogram").setLevel(logging.INFO)

    register_wizard_handlers(dp)
    register_catalog_handlers(dp)
    register_main_handlers(
        dp=dp,
        bot=bot,
        version=VERSION
    )

    # Запуск userbot, если сессия уже существует
    bot_info = await bot.get_me()
    bot_id = bot_info.id
    await try_start_userbot_from_config(USER_ID, bot_id)

    asyncio.create_task(gift_purchase_worker(bot))
    asyncio.create_task(userbot_gifts_updater(USER_ID))

    # Настройка стратегии повторных попыток подключения в случае ошибок
    # Используется для устойчивости к временным сбоям сети или сервера
    backoff_config = BackoffConfig(
        min_delay=1.0,
        max_delay=10.0,
        factor=2.0,
        jitter=0.2
    )
    await dp.start_polling(bot, backoff_config=backoff_config)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except Exception as exc:
        logger.critical(f"Критическая ошибка при запуске приложения: {exc}", exc_info=True)
        sys.exit(1)
