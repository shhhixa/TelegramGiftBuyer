"""
Модуль для настройки стандартного логирования в проекте.

Этот модуль содержит функции для:
- Инициализации логирования с заданным уровнем.
- Форматирования логов в удобочитаемом виде.

Основные функции:
- setup_logging: Настраивает стандартное логирование.
"""

# --- Стандартные библиотеки ---
import logging

def setup_logging(level: int = logging.INFO) -> None:
    """
    Инициализация стандартного логирования для проекта.

    :param level: Уровень логирования (по умолчанию logging.INFO)
    :return: None
    """
    logging.basicConfig(
        level=level,
        format="[{asctime}] [{levelname}] {name}: {message}",
        style="{",
        datefmt="%d.%m.%Y %H:%M:%S"
    )
