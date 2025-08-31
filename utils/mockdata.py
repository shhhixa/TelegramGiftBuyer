"""
Модуль для генерации тестовых данных.

Этот модуль содержит функции для:
- Генерации списка тестовых подарков.

Основные функции:
- generate_test_gifts: Генерирует список фейковых подарков для тестов и разработки.
"""

# --- Стандартные библиотеки ---
import random

def generate_test_gifts(count: int = 1) -> list[dict]:
    """
    Генерирует список тестовых (фейковых) подарков для использования в тестах и разработке.

    :param count: Количество подарков
    :return: Список словарей с параметрами подарков
    """
    gifts = []
    for i in range(count):
        gift = {
            "id": f"0000{i}",
            "price": 5000 + 1000 * random.choice([i, i, i, i, i, i, i, i, i, i + 1]),
            "supply": 9000 + 1000 * i,
            "left": 4000 + 1000 * i,
            "sticker_file_id": f"FAKE_FILE_ID_{i}",
            "emoji": "🎁"
        }
        gifts.append(gift)

    return gifts