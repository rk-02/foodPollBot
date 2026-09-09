"""Food poll bot package.

Modules:
    config      - environment + constants
    storage     - JSON-file persistence layer
    dishes      - global dish database helpers
    menu_config - editable per-weekday menu + poll time
    polls       - custom (inline-keyboard) poll engine
    stats       - "мне как обычно" statistics
    menu        - "Выберите действие" action menu
    admin       - private-chat admin panel
    scheduler   - daily poll / results loop
    bot         - FoodPollBot wiring everything together
"""
