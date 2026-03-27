# foodPollBot
Спасаем Никитоса от создания опросов вручную

## Тесты

Установить dev-зависимости:

```bash
pip install -r requirements-dev.txt
```

Полный прогон с покрытием:

```bash
pytest --cov=bot --cov-report=term-missing --cov-fail-under=95
```

Прогоны по слоям:

```bash
pytest -m unit
pytest -m integration
pytest -m e2e
```
