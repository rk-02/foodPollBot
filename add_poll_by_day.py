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

load_dotenv()

# Конфигурация
BOT_TOKEN = str(os.getenv('BOT_TOKEN'))
CHAT_ID = int(os.getenv('CHAT_ID')) # тестовый чат
#CHAT_ID = -1002391359004 # рабочий чат
TIMEZONE = pytz.timezone('Asia/Yekaterinburg')
POLL_START_HOUR = int(os.getenv('POLL_START_HOUR'))
POLL_START_MINUTES = int(os.getenv('POLL_START_MINUTES'))
POLL_SHIFT = int(os.getenv('POLL_SHIFT'))
    
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
        self.polls_dict = {}
        self.poll_ids = []

        # Регистрация обработчиков
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.callback_query.register(self.callback_get_results, lambda c: c.data == "get_results")
        self.dp.callback_query.register(self.callback_edit_poll, lambda c: c.data == "edit_poll")
        self.dp.callback_query.register(self.callback_change_start_poll_time, lambda c: c.data == "change_start_poll_time")
        self.dp.poll.register(self.handle_poll_update)
        #self.dp.poll_answer.register(self.handle_poll_update)
    
    def escape_markdown(self, text: str) -> str:
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{char}' if char in escape_chars else char for char in text)
        
    async def handle_poll_update(self,poll: types.Poll):
        if poll.id not in self.poll_ids:
            return

        print(f"""
        📊 Получено обновление опроса:
        ID: {poll.id}
        Вопрос: {poll.question}
        Варианты: {[o.text for o in poll.options]}
        Голоса: {[o.voter_count for o in poll.options]}
        Закрыт: {poll.is_closed}
        """)

        poll_name, poll_date = poll.question.rsplit(' ', 1)

        if poll_date not in self.polls_dict:
            self.polls_dict[poll_date] = {}
        
        if poll_name not in self.polls_dict[poll_date]:
            self.polls_dict[poll_date][poll_name] = {}

        self.polls_dict[poll_date][poll_name] = {
            'id': poll.id,
            'options': [o.text for o in poll.options],
            'votes': [o.voter_count for o in poll.options],
        }

        print(self.polls_dict)
    
    async def handle_poll_answer(self, poll_answer: types.PollAnswer):
        user_id = poll_answer.user.id
        first_name = poll_answer.user.first_name
        poll_id = poll_answer.poll_id
        chosen_options = poll_answer.option_ids  # Список ID выбранных вариантов (начиная с 0)

        print(poll_answer)
        
        print(f"Пользователь {first_name} (ID: {user_id}) проголосовал в опросе {poll_id}")
        print(f"Выбранные варианты: {chosen_options}")

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
                question=f'{current_poll['question']} {poll_date.strftime('%d.%m')}',
                options=current_poll['options'],
                is_anonymous=current_poll['is_anonymous']
            )
            
            self.poll_ids.append(sent_poll.poll.id)

    async def post_main_menu_buttons(self, chat_id):
        markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Получить результаты", callback_data="get_results")
             #types.InlineKeyboardButton(text="Редактировать опрос", callback_data="edit_poll"),
             #types.InlineKeyboardButton(text="Изменить время опросов", callback_data="change_start_poll_time")
             ]
        ])

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
        await callback_query.message.delete()
        chat_id = str(callback_query.message.chat.id)
        
        if chat_id in self.last_results_message:
            try:
                await self.last_results_message[chat_id].delete()
            except:
                pass

        date_string = ''
        now = datetime.now(TIMEZONE)

        if(now.hour <= POLL_START_HOUR  and now.minute <= POLL_START_MINUTES):
            date_string = now.strftime('%d.%m')
        else:
            now += timedelta(days=POLL_SHIFT)
            date_string = now.strftime('%d.%m') 

        message = f"🗓 *{self.escape_markdown(date_string)}*\n\n"

        if date_string in self.polls_dict:
            for poll_name, poll_data in self.polls_dict[date_string].items():
                message += f"🍽 *{self.escape_markdown(poll_name)}*:\n"
                
                for option, votes in zip(poll_data['options'], poll_data['votes']):
                    if votes == 0:
                        continue
                    message += f"  \- `{self.escape_markdown(option)}`: _{votes}_ голосов\n" 
                
                message += "\n"  
            
            self.last_results_message[chat_id] = await callback_query.message.answer(message, parse_mode="MarkdownV2")
        else:
            self.last_results_message[chat_id] = await callback_query.message.answer('Нет голосов')    

        await asyncio.sleep(1)
        await self.post_main_menu_buttons(callback_query.message.chat.id)

    async def callback_edit_poll(self, callback_query: types.CallbackQuery):
        await callback_query.message.delete()

        if self.last_get_poll_message:
            try:
                await self.last_get_poll_message.delete()
            except:
                pass

        self.last_get_poll_message = await callback_query.message.answer("Редактирование опроса")
        await asyncio.sleep(1)
        await self.post_main_menu_buttons(callback_query.message.chat.id)

    async def run(self):
        await self.dp.start_polling(self.bot)

async def shutdown(bot: TelegramBot):
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

   