"""Environment configuration and shared constants."""

import os

import pytz
from dotenv import load_dotenv

load_dotenv()

# --- Telegram / scheduling -------------------------------------------------

BOT_TOKEN = str(os.getenv("BOT_TOKEN", ""))
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yekaterinburg"))

# Default poll time - can be overridden at runtime through the admin panel
# (persisted in config.json). Kept as the fallback / first-run value.
POLL_START_HOUR = int(os.getenv("POLL_START_HOUR", "12"))
POLL_START_MINUTES = int(os.getenv("POLL_START_MINUTES", "0"))
DEFAULT_POLL_TIME = f"{POLL_START_HOUR:02d}:{POLL_START_MINUTES:02d}"

# How many days ahead a poll is for (1 = "food for tomorrow").
POLL_SHIFT = int(os.getenv("POLL_SHIFT", "1"))

# When the grouped result is posted to the group automatically.
RESULTS_HOUR = int(os.getenv("RESULTS_HOUR", "18"))
RESULTS_MINUTE = int(os.getenv("RESULTS_MINUTE", "0"))

# --- Domain constants ----------------------------------------------------

CATEGORIES = ["Первые блюда", "Вторые блюда", "Гарниры", "Салаты"]

CATEGORY_EMOJI = {
    "Первые блюда": "🍲",
    "Вторые блюда": "🍽",
    "Гарниры": "🍚",
    "Салаты": "🥗",
}

# Only Mon-Fri have menus (index == datetime.weekday()).
WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница"]

# "Мне как обычно" needs at least this many days between the first and last
# recorded order to be considered reliable.
USUAL_MIN_DAYS = 14

# Only look this far back when computing the "usual" choice.
USUAL_WINDOW_DAYS = 28
