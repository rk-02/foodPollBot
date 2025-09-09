# MongoDB Integration for FoodPollBot

Этот документ описывает, как настроить и использовать MongoDB с FoodPollBot.

## 🚀 Быстрый старт

### 1. Установка MongoDB

#### Windows:
```bash
# Скачайте MongoDB Community Server с официального сайта
# https://www.mongodb.com/try/download/community
# Или используйте chocolatey:
choco install mongodb
```

#### Linux (Ubuntu/Debian):
```bash
wget -qO - https://www.mongodb.org/static/pgp/server-7.0.asc | sudo apt-key add -
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt-get update
sudo apt-get install -y mongodb-org
sudo systemctl start mongod
sudo systemctl enable mongod
```

#### macOS:
```bash
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb/brew/mongodb-community
```

### 2. Установка зависимостей Python

```bash
pip install -r requirements.txt
```

### 3. Настройка конфигурации

Создайте или обновите файл `.env`:

```env
# Telegram Bot Configuration
BOT_TOKEN=your_bot_token_here
CHAT_ID=-1001234567890
TIMEZONE=Asia/Yekaterinburg

# Poll Scheduling Configuration
POLL_START_HOUR=16
POLL_START_MINUTES=35
POLL_SHIFT=1

# MongoDB Configuration
MONGO_URL=mongodb://localhost:27017
MONGO_DB_NAME=foodpoll_bot
MONGO_CONNECTION_TIMEOUT=10000
```

### 4. Миграция данных

```bash
# Тест подключения к MongoDB
python migrate_to_mongo.py test

# Миграция данных из schedule.json
python migrate_to_mongo.py migrate

# Просмотр конфигурации
python migrate_to_mongo.py config
```

### 5. Запуск бота

```bash
python add_poll_by_day.py
```

## 📊 Структура данных MongoDB

### Коллекции:

1. **menu_items** - пункты меню
2. **polls** - опросы
3. **user_votes** - голоса пользователей
4. **poll_results** - агрегированные результаты

### Примеры документов:

#### menu_items:
```json
{
  "_id": "ObjectId",
  "category": "Вторые блюда",
  "name": "Гуляш",
  "description": "",
  "is_active": true,
  "display_order": 5,
  "created_at": "2025-09-08T12:00:00Z",
  "updated_at": "2025-09-08T12:00:00Z"
}
```

#### polls:
```json
{
  "_id": "poll_telegram_id",
  "category": "Вторые блюда",
  "poll_date": "08.09",
  "question": "Вторые блюда 08.09",
  "options": [
    {"index": 0, "text": "Гуляш", "voter_count": 5},
    {"index": 1, "text": "Котлета", "voter_count": 3}
  ],
  "is_anonymous": false,
  "is_closed": false,
  "total_voter_count": 8,
  "created_at": "2025-09-08T12:00:00Z",
  "updated_at": "2025-09-08T12:05:00Z"
}
```

#### user_votes:
```json
{
  "_id": "ObjectId",
  "poll_id": "poll_telegram_id",
  "user_id": 123456789,
  "user_name": "John",
  "option_indices": [0],
  "option_texts": ["Гуляш"],
  "voted_at": "2025-09-08T12:03:00Z"
}
```

## 🔧 Администрирование

### Подключение к MongoDB через MongoDB Compass

1. Скачайте MongoDB Compass
2. Подключитесь к `mongodb://localhost:27017`
3. Выберите базу данных `foodpoll_bot`

### Полезные команды MongoDB

```javascript
// Показать все коллекции
show collections

// Количество пунктов меню по категориям
db.menu_items.aggregate([
  {$group: {_id: "$category", count: {$sum: 1}}},
  {$sort: {_id: 1}}
])

// Активные опросы
db.polls.find({is_closed: false})

// Статистика голосований по дате
db.user_votes.aggregate([
  {$group: {_id: {$dateToString: {format: "%Y-%m-%d", date: "$voted_at"}}, count: {$sum: 1}}},
  {$sort: {_id: -1}}
])

// Удалить старые данные (старше 30 дней)
db.user_votes.deleteMany({
  voted_at: {$lt: new Date(Date.now() - 30*24*60*60*1000)}
})
```

## 🛠️ Устранение неполадок

### Проблема: "Connection refused"
```bash
# Убедитесь, что MongoDB запущен
sudo systemctl status mongod  # Linux
brew services list | grep mongodb  # macOS

# Запустите MongoDB если не запущен
sudo systemctl start mongod  # Linux
brew services start mongodb/brew/mongodb-community  # macOS
```

### Проблема: "Authentication failed"
```bash
# Если MongoDB настроен с аутентификацией, обновите MONGO_URL:
MONGO_URL=mongodb://username:password@localhost:27017
```

### Проблема: "Database not accessible"
```bash
# Проверьте права доступа к директории данных MongoDB
sudo chown -R mongodb:mongodb /var/lib/mongodb  # Linux
```

## 📈 Мониторинг и логи

### Просмотр логов MongoDB:
```bash
# Linux
sudo tail -f /var/log/mongodb/mongod.log

# macOS
tail -f /usr/local/var/log/mongodb/mongo.log
```

### Логи бота:
Бот выводит информацию о подключении к MongoDB в консоль при запуске.

## 🔄 Backup и восстановление

### Создание резервной копии:
```bash
mongodump --db foodpoll_bot --out ./backup/
```

### Восстановление из резервной копии:
```bash
mongorestore --db foodpoll_bot ./backup/foodpoll_bot/
```

## 📝 Дополнительные возможности

### Добавление нового пункта меню через MongoDB:
```javascript
db.menu_items.insertOne({
  category: "Вторые блюда",
  name: "Новое блюдо",
  description: "Описание нового блюда",
  is_active: true,
  display_order: 100,
  created_at: new Date(),
  updated_at: new Date()
})
```

### Деактивация пункта меню:
```javascript
db.menu_items.updateOne(
  {name: "Устаревшее блюдо"},
  {$set: {is_active: false, updated_at: new Date()}}
)
```

## 📞 Поддержка

Если у вас возникли проблемы:
1. Проверьте логи MongoDB и бота
2. Убедитесь, что все зависимости установлены
3. Проверьте конфигурацию в `.env` файле
4. Используйте `python migrate_to_mongo.py test` для диагностики