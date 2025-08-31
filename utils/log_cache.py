"""Утилита для кеширования последних строк логов в памяти.

Модуль предоставляет:
- LogCacheHandler: logging.Handler, сохраняющий N последних отформатированных строк в памяти (deque).
- LOG_CACHE_HANDLER: синглтон для быстрой регистрации в корневом логгере.
- get_cached_lines / get_cached_text: функции для получения кеша логов.

Кеш хранится в памяти и теряется при перезапуске процесса.
"""

import logging
import threading
from collections import deque
from typing import List


class LogCacheHandler(logging.Handler):
    """Handler логирования, который хранит последние N отформатированных строк в памяти.

    Потоко-безопасен: использует блокировку для доступа к внутреннему deque.
    """

    def __init__(self, capacity: int = 50, level: int = logging.INFO):
        super().__init__(level)
        self._lock = threading.Lock()
        self._lines = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        """Добавить отформатированную запись в кеш.

        В случае ошибки форматирования используется упрощённое представление.
        """
        try:
            msg = self.format(record)
        except Exception:
            msg = f"{record.levelname}: {record.getMessage()}"
        with self._lock:
            self._lines.append(msg)

    def get_lines(self) -> List[str]:
        """Вернуть список кешированных строк (от старых к новым)."""
        with self._lock:
            return list(self._lines)

    def get_text(self, sep: str = "\n") -> str:
        """Вернуть кеш как единый текст, строки разделяются `sep`."""
        return sep.join(self.get_lines())


# Синглтон-объект: модульные импорты могут регистрировать этот handler в корневом логгере
LOG_CACHE_HANDLER = LogCacheHandler(capacity=50, level=logging.DEBUG)

# По умолчанию задаём форматтер, соответствующий формату в utils.logging.setup_logging
LOG_CACHE_HANDLER.setFormatter(
    logging.Formatter(
        "[{asctime}] [{levelname}] {name}: {message}",
        style="{",
        datefmt="%d.%m.%Y %H:%M:%S",
    )
)

def get_cached_lines() -> List[str]:
    """Вернуть кешированные строки как список (от старых к новым)."""
    return LOG_CACHE_HANDLER.get_lines()


def get_cached_text(sep: str = "\n") -> str:
    """Вернуть кеш логов как единый текст.

    :param sep: разделитель между строками в результирующем тексте
    :return: строка с кешированными логами
    """
    return LOG_CACHE_HANDLER.get_text(sep=sep)


__all__ = ["LogCacheHandler", "LOG_CACHE_HANDLER", "get_cached_lines", "get_cached_text"]
