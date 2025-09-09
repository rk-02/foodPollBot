"""
MongoDB Schema Definition for FoodPollBot

Collections:
1. menu_items - хранение пунктов меню
2. polls - хранение опросов
3. poll_results - хранение результатов голосования
4. user_votes - хранение голосов пользователей
"""

# Collection: menu_items
# Документ описывает пункт меню
MENU_ITEM_SCHEMA = {
    "_id": "ObjectId",  # MongoDB ID
    "category": "str",  # "Первые блюда", "Вторые блюда", "Гарниры", "Салаты"
    "name": "str",      # Название блюда
    "description": "str",  # Описание (опционально)
    "is_active": "bool",   # Активен ли пункт меню
    "display_order": "int",  # Порядок отображения
    "created_at": "datetime",
    "updated_at": "datetime"
}

# Collection: polls
# Документ описывает опрос
POLL_SCHEMA = {
    "_id": "str",  # Telegram poll ID как строка
    "category": "str",  # Категория опроса ("Первые блюда", etc.)
    "poll_date": "date",  # Дата опроса в формате "DD.MM"
    "question": "str",    # Текст вопроса
    "options": [          # Варианты ответов
        {
            "index": "int",      # Индекс варианта
            "text": "str",       # Текст варианта
            "voter_count": "int" # Количество голосов
        }
    ],
    "is_anonymous": "bool",
    "is_closed": "bool",
    "total_voter_count": "int",
    "created_at": "datetime",
    "updated_at": "datetime"
}

# Collection: user_votes
# Документ описывает голос пользователя
USER_VOTE_SCHEMA = {
    "_id": "ObjectId",
    "poll_id": "str",        # ID опроса
    "user_id": "int",        # Telegram user ID
    "user_name": "str",      # Имя пользователя
    "option_indices": ["int"],  # Индексы выбранных вариантов
    "option_texts": ["str"],    # Тексты выбранных вариантов
    "voted_at": "datetime"
}

# Collection: poll_results
# Агрегированные результаты по дням
POLL_RESULTS_SCHEMA = {
    "_id": "str",  # Дата в формате "DD.MM"
    "date": "str", # Дата опроса
    "categories": {
        "Первые блюда": {
            "poll_id": "str",
            "options": [
                {
                    "text": "str",
                    "votes": "int"
                }
            ]
        },
        "Вторые блюда": "...",
        "Гарниры": "...",
        "Салаты": "..."
    },
    "user_combinations": {  # Комбинации выборов пользователей (для "set_dish")
        "user_id": {
            "Вторые блюда": ["str"],
            "Гарниры": ["str"]
        }
    },
    "created_at": "datetime",
    "updated_at": "datetime"
}

# Индексы для оптимизации
INDEXES = {
    "menu_items": [
        {"category": 1, "is_active": 1},
        {"display_order": 1}
    ],
    "polls": [
        {"poll_date": 1},
        {"category": 1, "poll_date": 1}
    ],
    "user_votes": [
        {"poll_id": 1, "user_id": 1},
        {"user_id": 1, "voted_at": -1},
        {"poll_id": 1}
    ],
    "poll_results": [
        {"date": 1}
    ]
}