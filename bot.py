"""Entry point.

All logic lives in the ``app`` package:

    app.config       env + constants
    app.storage      JSON persistence
    app.dishes       global dish database
    app.menu_config  poll time + editable per-weekday menu
    app.polls        custom (inline-keyboard) poll engine
    app.stats        "Мне как обычно"
    app.menu         "Выберите действие" action menu
    app.admin        private-chat admin panel
    app.scheduler    daily poll / results loop
    app.bot          FoodPollBot
"""

import asyncio
import logging

from app.bot import FoodPollBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main() -> None:  # pragma: no cover - runtime entry point
    asyncio.run(FoodPollBot().run())


if __name__ == "__main__":  # pragma: no cover
    main()
