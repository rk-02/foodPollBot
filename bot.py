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

If a run crashes (e.g. a network blip reaching api.telegram.org kills
``dp.start_polling`` outright), it is restarted with backoff instead of
taking the whole process down — Ctrl+C / SIGTERM still stop it for good.
"""

import asyncio
import logging
import time

from app.bot import FoodPollBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

log = logging.getLogger(__name__)

MIN_BACKOFF = 5
MAX_BACKOFF = 60
# a run that survives this long is treated as healthy -> backoff resets
HEALTHY_RUN_SECONDS = 300


def main() -> None:  # pragma: no cover - runtime entry point
    backoff = MIN_BACKOFF
    while True:
        started = time.monotonic()
        try:
            asyncio.run(FoodPollBot().run())
            log.warning("run() returned without an exception — stopping")
            return
        except (KeyboardInterrupt, SystemExit):
            log.info("stopped")
            return
        except Exception:
            log.exception("bot crashed, restarting in %ss", backoff)
            if time.monotonic() - started > HEALTHY_RUN_SECONDS:
                backoff = MIN_BACKOFF
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)


if __name__ == "__main__":  # pragma: no cover
    main()
