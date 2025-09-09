import asyncio
import signal
from datetime import datetime, timedelta
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import json
from typing import Dict, Optional
import os
import logging
from dotenv import load_dotenv
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Import MongoDB infrastructure
from infrastructure.config import load_config
from infrastructure.mongo_storage import MongoStorage
from infrastructure.menu_manager import MenuManager

load_dotenv()

# Load configuration
config = load_config()

# Конфигурация
BOT_TOKEN = config.bot.bot_token
CHAT_ID = config.bot.chat_id
TIMEZONE = pytz.timezone(config.bot.timezone)
POLL_START_HOUR = config.bot.poll_start_hour
POLL_START_MINUTES = config.bot.poll_start_minutes
POLL_SHIFT = config.bot.poll_shift
    
with open("schedule.json", "r", encoding="utf-8") as file:
    POLLS = json.load(file)

class TelegramBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.dp = Dispatcher()
        self.last_results_message: Dict[str, int] = {}
        self.last_get_poll_message = None
        self.poll_chats = set()
        self.poll_task = None
        self.last_polls: Dict[int, int] = {}
        
        # MongoDB storage and menu manager
        self.storage = MongoStorage(config.mongo)
        self.menu_manager = MenuManager(self.storage)
        self.mongodb_available = False  # Will be set to True if MongoDB connects successfully
        
        # Legacy data structures for compatibility
        self.polls_dict = {}
        self.poll_ids = []
        self.set_dish = {}
        self.poll_info_by_id = {}

        # Регистрация обработчиков
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.callback_query.register(self.callback_get_results, lambda c: c.data == "get_results")
        self.dp.callback_query.register(self.callback_get_joint_results, lambda c: c.data == "get_group_results")
        self.dp.callback_query.register(self.callback_edit_poll, lambda c: c.data == "edit_poll")
        self.dp.callback_query.register(self.callback_change_start_poll_time, lambda c: c.data == "change_start_poll_time")
        self.dp.poll.register(self.handle_poll_update)
        self.dp.poll_answer.register(self.handle_poll_answer)
        self.dp.message.register(self.handle_text_message) # обработчик на сообщения

    async def initialize(self):
        """Инициализация бота и подключение к базе данных"""
        try:
            # Подключение к MongoDB
            await self.storage.connect()
            print("Connected to MongoDB successfully")
            
            # Инициализация меню из schedule.json
            await self.menu_manager.initialize_menu_from_json()
            print("Menu initialized from schedule.json")
            
        except Exception as e:
            print(f"Failed to initialize bot: {e}")
            raise
    
    async def cleanup(self):
        """Очистка ресурсов"""
        if self.mongodb_available:
            await self.storage.disconnect()
            print("🔌 Disconnected from MongoDB")

    
    def escape_markdown(self, text: str) -> str:
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{char}' if char in escape_chars else char for char in text)
    
    async def handle_text_message(self, message: types.Message):
        if(message.text == '?'):
            menu = await self.get_joint_results()
            await message.answer(menu, parse_mode="MarkdownV2")
            
        
    async def handle_poll_update(self, poll: types.Poll):
        if poll.id not in self.poll_ids:
            return

        # сплитим вопрос на текст + дату
        poll_name, poll_date = poll.question.rsplit(' ', 1)

        # Save to MongoDB only if available
        if self.mongodb_available:
            try:
                await self.menu_manager.save_poll_data(
                    poll_id=str(poll.id),
                    category=poll_name,
                    poll_date=poll_date,
                    question=poll.question,
                    options=options,
                    votes=votes
                )
            except Exception as e:
                print(f"Failed to save poll data to MongoDB: {e}")

        # Legacy: Заполняем основной словарь
        options = [o.text for o in poll.options]
        votes = [o.voter_count for o in poll.options]
        date_bucket = self.polls_dict.setdefault(poll_date, {})
        date_bucket.setdefault('set_dish', {})
        date_bucket.setdefault(poll_name, {}).update({
            'id':      poll.id,
            'options': options,
            'votes':   votes,
        })

        # Legacy: Заполняем обратную мапу для быстрого поиска по ID
        self.poll_info_by_id[str(poll.id)] = {
            'poll_question': poll_name,
            'poll_date': poll_date
        }

        print(self.polls_dict)

    async def handle_poll_answer(self, poll_answer: types.PollAnswer):
        user_id = poll_answer.user.id
        first_name = poll_answer.user.first_name
        poll_id = str(poll_answer.poll_id)
        chosen_options = poll_answer.option_ids

        print(f"Пользователь {first_name} (ID: {user_id}) проголосовал в опросе {poll_id}")
        print(f"Выбранные варианты (индексы): {chosen_options}")

        info = self.poll_info_by_id.get(poll_id)
        if not info:
            print(f"Не найдено info для poll_id={poll_id}")
            return

        question = info['poll_question']   # «Вторые блюда» или «Гарниры»
        date = info['poll_date']

        # текстовые варианты для этого опроса
        options = self.polls_dict[date][question]['options']
        chosen_texts = [options[i] for i in chosen_options]

        # Save to MongoDB only if available
        if self.mongodb_available:
            try:
                await self.menu_manager.save_user_vote_data(
                    poll_id=poll_id,
                    user_id=user_id,
                    user_name=first_name,
                    option_indices=chosen_options,
                    poll_date=date,
                    category=question,
                    options=options
                )
            except Exception as e:
                print(f"Failed to save user vote to MongoDB: {e}")

        # Legacy: Update in-memory data for compatibility
        if question in ('Вторые блюда', 'Гарниры'):
            # 1) гарантируем, что на уровне даты есть словарь set_dish
            sd = self.polls_dict[date].setdefault('set_dish', {})

            # 2) гарантируем, что в нём есть запись для этого user_id
            user_entry = sd.setdefault(user_id, {})

            # 3) добавляем/обновляем выбор под ключом вопроса
            user_entry[question] = chosen_texts

        # отладочный вывод: теперь в self.polls_dict[date]['set_dish'][user_id]
        # будет что-то вроде {'Вторые блюда': [...], 'Гарниры': [...]}
        print(f"Состояние set_dish для даты {date}:")
        print(self.polls_dict[date]['set_dish'])

    async def save_poll_id(self, chat_id: int, message_id: int):
        self.last_polls[chat_id] = message_id

    async def get_poll_results(self, bot, chat_id: int) -> Optional[types.Poll]:
        print(f"Тип last_polls: {type(self.last_polls)}")  # Должен быть dict
        print(f"Содержимое: {self.last_polls}")  # Проверьте структуру данных
        print(chat_id)

        message_id = self.last_polls.get(chat_id)
        
        if not message_id:
            return None

        try:
            msg = await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None  # Просто убираем кнопки
            )
            return msg.poll
        except:
            return None

    async def start_poll_scheduler(self, chat_id=None):
        if chat_id:
            self.poll_chats.add(chat_id)

        if not self.poll_task or self.poll_task.done():
            self.poll_task = asyncio.create_task(self._poll_scheduler())

    async def _poll_scheduler(self):
        while True:
            now = datetime.now(TIMEZONE)

            print(now.hour, now.minute)

            if(now.hour == POLL_START_HOUR  and now.minute == POLL_START_MINUTES):
                self.poll_ids = []
                await self._send_scheduled_poll()
            await asyncio.sleep(60)

    async def _send_scheduled_poll(self):
        now = datetime.now(TIMEZONE)

        poll_index = (now.weekday() + POLL_SHIFT) % 7

        if (poll_index == 5 or poll_index == 6):
            print('weekday ', poll_index)
            return

        print("Sending poll...")

        poll_date = datetime.now() + timedelta(days=POLL_SHIFT)

        polls = POLLS[poll_index]
        for current_poll in polls:
            sent_poll = await self.bot.send_poll(
                chat_id=CHAT_ID,
                question=f"{current_poll['question']} {poll_date.strftime('%d.%m')}",
                options=current_poll['options'],
                is_anonymous=current_poll['is_anonymous']
            )
            
            self.poll_ids.append(sent_poll.poll.id)

        await self.bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

    # Обработчики
    async def cmd_start(self, message: types.Message):
        if message.chat.type == 'supergroup':
            await self.start_poll_scheduler(message.chat.id)
            await message.answer("Бот запущен!")
            #await message.answer(f"Опрос запланирован на {POLL_START_HOUR}:{POLL_START_MINUTES}")
            #await self.post_main_menu_buttons(message.chat.id)
        elif message.chat.type == 'private':
            await self.post_main_menu_buttons(message.chat.id)
    
    async def callback_change_start_poll_time(self, callback_query: types.CallbackQuery):
        await callback_query.message.answer('Напишите время проведения опроса в формате ЧЧ:MM \nПример 12:00')
        

    async def callback_get_results(self, callback_query: types.CallbackQuery):
        # Удаляем предыдущее сообщение с меню, если есть
        try:
            await callback_query.message.delete()
        except:
            pass

        chat_id = str(callback_query.message.chat.id)

        # Удаляем предыдущий вывод результатов
        if chat_id in self.last_results_message:
            try:
                await self.last_results_message[chat_id].delete()
            except:
                pass

        # Вычисляем дату «дня питания»
        now = datetime.now(TIMEZONE)
        if now.hour < POLL_START_HOUR and now.minute < POLL_START_MINUTES:
            date_string = now.strftime('%d.%m')
        else:
            now += timedelta(days=POLL_SHIFT)
            date_string = now.strftime('%d.%m')

        # Начинаем собирать сообщение
        message = f"🗓 *{self.escape_markdown(date_string)}*\n\n"

        if date_string in self.polls_dict:
            for poll_name, poll_data in self.polls_dict[date_string].items():
                # Пропускаем служебный ключ set_dish
                if 'options' not in poll_data or 'votes' not in poll_data:
                    continue

                message += f"🍽 *{self.escape_markdown(poll_name)}*:\n"
                for option, votes in zip(poll_data['options'], poll_data['votes']):
                    if votes == 0:
                        continue
                    message += f"  \\- `{self.escape_markdown(option)}`: _{votes}_ голосов\n"
                message += "\n"

            # Если после фильтрации ничего не добавилось
            if message.strip().endswith(f"*{self.escape_markdown(date_string)}*"):
                message += "Нет голосов."

            self.last_results_message[chat_id] = await callback_query.message.answer(
                message, parse_mode="MarkdownV2"
            )
        else:
            self.last_results_message[chat_id] = await callback_query.message.answer("Нет голосов")

        # Показываем главное меню через секунду
        await asyncio.sleep(1)
        await self.post_main_menu_buttons(callback_query.message.chat.id)
    
    async def get_joint_results(self):

        # Вычисляем нужную дату в формате 'дд.мм'
        now = datetime.now(TIMEZONE)
        if now.hour < POLL_START_HOUR and now.minute < POLL_START_MINUTES:
            date_string = now.strftime('%d.%m')
        else:
            now += timedelta(days=POLL_SHIFT)
            date_string = now.strftime('%d.%m')

        # Собираем сообщение
        header = f"🗓 *{self.escape_markdown(date_string)}*\n\n"
        body = ""

        # Если по этой дате есть голоса
        try:
            # Try to get data from MongoDB first (only if available)
            if self.mongodb_available:
                results = await self.menu_manager.get_poll_results_for_date(date_string)
                
                if results and results.get('polls'):
                    # Use MongoDB data
                    first_poll = results['polls'].get('Первые блюда')
                    if first_poll and first_poll.get('options'):
                        body += "🍲 *Первые блюда:*\n"
                        for option in first_poll['options']:
                            body += f"  \\- `{self.escape_markdown(option['text'])}`: _{option['votes']}_\n"
                        body += "\n"
                        
                    salad_poll = results['polls'].get('Салаты')
                    if salad_poll and salad_poll.get('options'):
                        body += "🥗 *Салаты:*\n"
                        for option in salad_poll['options']:
                            body += f"  \\- `{self.escape_markdown(option['text'])}`: _{option['votes']}_\n"
                    body += "\n"

                    # User combinations from MongoDB
                    user_combinations = results.get('user_combinations', {})
                    if user_combinations:
                        body += "🍽️ *Вторые блюда\\(комплекты\\):*\n"
                        i = 1
                        for user_id, choices in user_combinations.items():
                            main_list = choices.get('Вторые блюда', ['—'])
                            side_list = choices.get('Гарниры', ['—'])
                            main = main_list[0] if main_list else '—'
                            side = side_list[0] if side_list else '—'

                            if(main == '—'):
                                body += f"{i}\\. {self.escape_markdown(side)}\n"
                            elif(side == '—'):
                                body += f"{i}\\. {self.escape_markdown(main)}\n"
                            elif(main != '—' and side != '—'):
                                body += f"{i}\\. `{self.escape_markdown(main)}` \\+ `{self.escape_markdown(side)}`\n"
                            i += 1
                    else:
                        if not body or body.strip() == "":
                            body = "Нет голосов"
                    return header + body

            # Fallback to legacy data (always available)
            bucket = self.polls_dict.get(date_string, {})
            set_dish = bucket.get('set_dish', {})

            first_poll = bucket.get('Первые блюда')
            if first_poll and 'options' in first_poll:
                body += "🍲 *Первые блюда:*\n"
                for opt, cnt in zip(first_poll['options'], first_poll['votes']):
                    if cnt:
                        body += f"  \\- `{self.escape_markdown(opt)}`: _{cnt}_\n"
                body += "\n"
                
            salad_poll = bucket.get('Салаты')
            if salad_poll and 'options' in salad_poll:
                body += "🥗 *Салаты:*\n"
                for opt, cnt in zip(salad_poll['options'], salad_poll['votes']):
                    if cnt:
                        body += f"  \\- `{self.escape_markdown(opt)}`: _{cnt}_\n"
            body += "\n"

            if set_dish:
                body += "🍽️ *Вторые блюда\\(комплекты\\):*\n"
                i = 1
                for user_id, choices in set_dish.items():
                    main_list = choices.get('Вторые блюда', ['—'])
                    side_list = choices.get('Гарниры', ['—'])
                    main = main_list[0] if main_list else '—'
                    side = side_list[0] if side_list else '—'

                    if(main == '—'):
                        body += f"{i}\\. {self.escape_markdown(side)}\n"
                    elif(side == '—'):
                        body += f"{i}\\. {self.escape_markdown(main)}\n"
                    elif(main != '—' and side != '—'):
                        body += f"{i}\\. `{self.escape_markdown(main)}` \\+ `{self.escape_markdown(side)}`\n"
                    i += 1
            else:
                if not body or body.strip() == "":
                    body = "Нет голосов"
                    
        except Exception as e:
            print(f"Error getting results: {e}")
            # Final fallback to simple message
            body = "Нет голосов"

        # Отправляем и сохраняем ссылку на сообщение
        msg = header + body

        return msg
        

    async def callback_get_joint_results(self, callback_query: types.CallbackQuery):
         # Удаляем старое сообщение с кнопками, если есть
        try:
            await callback_query.message.delete()
        except:
            pass

        chat_id = str(callback_query.message.chat.id)

        # Удаляем предыдущий вывод результатов
        if chat_id in self.last_results_message:
            try:
                await self.last_results_message[chat_id].delete()
            except:
                pass

        menu =  await self.get_joint_results()

        self.last_results_message[chat_id] = await callback_query.message.answer(
            menu, parse_mode="MarkdownV2"
        )

        # Через секунду показываем главное меню
        await asyncio.sleep(1)
        await self.post_main_menu_buttons(callback_query.message.chat.id)

    async def callback_edit_poll(self, callback_query: types.CallbackQuery):
        try:
            await callback_query.message.delete()
        except:
            pass
        
        if self.last_get_poll_message:
            try:
                await self.last_get_poll_message.delete()
            except:
                pass

        self.last_get_poll_message = await callback_query.message.answer("Редактирование опроса")
        await asyncio.sleep(1)
        await self.post_main_menu_buttons(callback_query.message.chat.id)

    async def run(self):
        await self.initialize()
        try:
            await self.dp.start_polling(self.bot)
        finally:
            await self.cleanup()

    async def post_main_menu_buttons(self, chat_id):
        markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Получить результаты", callback_data="get_results"),
             types.InlineKeyboardButton(text="Сгруппированный результат", callback_data="get_group_results")
             #types.InlineKeyboardButton(text="Редактировать опрос", callback_data="edit_poll"),
             #types.InlineKeyboardButton(text="Изменить время опросов", callback_data="change_start_poll_time")
             ]
        ])

        await self.bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

async def shutdown(bot: TelegramBot):
    if hasattr(bot, 'mongodb_available') and bot.mongodb_available:
        await bot.cleanup()
    await bot.bot.close()

if __name__ == "__main__":    
    bot = TelegramBot()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        loop.run_until_complete(shutdown(bot))
    finally:
        loop.close()

   