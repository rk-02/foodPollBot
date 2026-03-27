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
import time
import uuid
from dotenv import load_dotenv
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import BotCommand

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


def _dbg(location: str, message: str, data: dict, run_id: str, hypothesis_id: str) -> None:  # pragma: no cover
    # region agent log
    try:
        payload = {
            "sessionId": "e7ee70",
            "id": f"log_{uuid.uuid4().hex}",
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": data,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
        }
        with open("debug-e7ee70.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion agent log

class Poll:  # pragma: no cover
    async def _poll_scheduler():
        while True:

            now = datetime.now(TIMEZONE)

            print(now.hour, now.minute)

            poll_index = (now.weekday() + POLL_SHIFT) % 7

            if (poll_index == 5 or poll_index == 6):
                await asyncio.sleep(60)
                continue

            if now.hour == this.REMINDER_HOUR and now.minute == this.REMINDER_MINUTES:
                await self.bot.send_message(
                    chat_id=CHAT_ID,
                    text="Напоминалка, результаты отправятся в 18:00"
                )
            
            if now.hour == this.SEND_HOUR and now.minute == SEND_HOUR:
                menu = await self.get_joint_results()

                await self.bot.send_message(
                    chat_id=CHAT_ID,
                    text=menu,
                    parse_mode="MarkdownV2"
                )

            if(now.hour == POLL_START_HOUR and now.minute == POLL_START_MINUTES):
                self.poll_ids = []
                await self._send_scheduled_poll()
            await asyncio.sleep(60)


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

    
    def escape_markdown(self, text: str) -> str:
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{char}' if char in escape_chars else char for char in text)
    
    async def handle_text_message(self, message: types.Message):
        target_stickers = ['AgADMAADr8ZRGg']

        if message.text == '?' or (message.sticker and message.sticker.file_unique_id in target_stickers):
            #menu = await self.get_joint_results()
            message_text = 'Результат отправится автоматически в 18:00'
            await message.answer(message_text, parse_mode="MarkdownV2")
    
    async def handle_poll_update(self, poll: types.Poll):
        run_id = "simultaneous_vote_v1"
        _dbg(
            "bot.py:handle_poll_update:entry",
            "poll update received",
            {"poll_id": str(poll.id), "question": poll.question},
            run_id,
            "H1",
        )
        if poll.id not in self.poll_ids:
            _dbg(
                "bot.py:handle_poll_update:skip_unknown_poll",
                "poll not in tracked ids",
                {"poll_id": str(poll.id), "tracked_count": len(self.poll_ids)},
                run_id,
                "H3",
            )
            return

        poll_name, poll_date = poll.question.rsplit(' ', 1)

        date_bucket = self.polls_dict.setdefault(poll_date, {})

        date_bucket.setdefault('set_dish', {})

        date_bucket.setdefault(poll_name, {}).update({
            'id':      poll.id,
            'options': [o.text for o in poll.options],
            'votes':   [o.voter_count for o in poll.options],
        })

        self.poll_info_by_id[str(poll.id)] = {
            'poll_question': poll_name,
            'poll_date': poll_date
        }
        _dbg(
            "bot.py:handle_poll_update:stored_info",
            "poll info stored",
            {
                "poll_id": str(poll.id),
                "poll_name": poll_name,
                "poll_date": poll_date,
                "known_info_count": len(self.poll_info_by_id),
            },
            run_id,
            "H1",
        )

        print(self.polls_dict)

    async def handle_poll_answer(self, poll_answer: types.PollAnswer):
        run_id = "simultaneous_vote_v1"
        user_id = poll_answer.user.id
        first_name = poll_answer.user.first_name
        poll_id = str(poll_answer.poll_id)
        chosen_options = poll_answer.option_ids
        _dbg(
            "bot.py:handle_poll_answer:entry",
            "poll answer received",
            {"poll_id": poll_id, "user_id": user_id, "option_ids": chosen_options},
            run_id,
            "H2",
        )

        now = datetime.now(TIMEZONE)

        print(now.hour, now.minute)
        print(f"Пользователь {first_name} (ID: {user_id}) проголосовал в опросе {poll_id}")
        print(f"Выбранные варианты (индексы): {chosen_options}")

        info = self.poll_info_by_id.get(poll_id)
        if not info:
            print(f"Не найдено info для poll_id={poll_id}")
            _dbg(
                "bot.py:handle_poll_answer:missing_info",
                "poll info missing for answer",
                {"poll_id": poll_id, "known_info_count": len(self.poll_info_by_id)},
                run_id,
                "H1",
            )
            return

        question = info['poll_question']   # «Вторые блюда» или «Гарниры»
        date = info['poll_date']

        # текстовые варианты для этого опроса
        options = self.polls_dict[date][question]['options']
        chosen_texts = [options[i] for i in chosen_options]
        _dbg(
            "bot.py:handle_poll_answer:resolved_choice",
            "resolved answer to texts",
            {
                "poll_id": poll_id,
                "question": question,
                "date": date,
                "chosen_texts": chosen_texts,
            },
            run_id,
            "H2",
        )

        if question in ('Вторые блюда', 'Гарниры'):
            # 1) гарантируем, что на уровне даты есть словарь set_dish
            sd = self.polls_dict[date].setdefault('set_dish', {})

            # 2) гарантируем, что в нём есть запись для этого user_id
            user_entry = sd.setdefault(user_id, {})

            # 3) добавляем/обновляем выбор под ключом вопроса
            user_entry[question] = chosen_texts
            _dbg(
                "bot.py:handle_poll_answer:user_entry_updated",
                "updated set_dish user entry",
                {
                    "date": date,
                    "user_id": user_id,
                    "user_entry_keys": list(user_entry.keys()),
                    "user_entry": user_entry,
                    "set_dish_users_count": len(sd),
                },
                run_id,
                "H4",
            )

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

    async def _poll_scheduler(self):  # pragma: no cover
        while True:
            now = datetime.now(TIMEZONE)

            print(now.hour, now.minute)

            poll_index = (now.weekday() + POLL_SHIFT) % 7

            if (poll_index == 5 or poll_index == 6):
                await asyncio.sleep(60)
                continue

            if now.hour == 17 and now.minute == 00:
                await self.bot.send_message(
                    chat_id=CHAT_ID,
                    text="Напоминалка, результаты отправятся в 18:00"
                )
            
            if now.hour == 18 and now.minute == 00:
                menu = await self.get_joint_results()

                await self.bot.send_message(
                    chat_id=CHAT_ID,
                    text=menu,
                    parse_mode="MarkdownV2"
                )

            if(now.hour == POLL_START_HOUR and now.minute == POLL_START_MINUTES):
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

    # Обработчики
    async def cmd_start(self, message: types.Message):
        if message.chat.type == 'supergroup':
            await self.start_poll_scheduler(message.chat.id)
            await message.answer("Бот запущен!")
            await self.post_group_menu_buttons(message.chat.id)
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
            # Для каждого пользователя выводим его выбор гарнира + второго блюда
            i = 1
            for user_id, choices in set_dish.items():
                # Получаем оба варианта — если пользователь ещё не ответил на какую-то часть,
                # подставляем «—»
                main_choices = choices.get('Вторые блюда') or ['—']
                side_choices = choices.get('Гарниры') or ['—']
                main = main_choices[0] if len(main_choices) > 0 else '—'
                side = side_choices[0] if len(side_choices) > 0 else '—'

                if(main == '—'):
                    body += (
                        f"{i}\\. {self.escape_markdown(side)}\n"
                    )
                
                if(side == '—'):
                    body += (
                        f"{i}\\. {self.escape_markdown(main)}\n"
                    )

                if(main != '—' and side != '—'):
                    body += (
                        f"{i}\\. `{self.escape_markdown(main)}` \\+ `{self.escape_markdown(side)}`\n"
                    )

                i = i + 1
        else:
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

        if callback_query.message.chat.type == 'supergroup':
            user = callback_query.from_user
            name = user.first_name or user.username or f"ID{user.id}"
            if user.last_name:
                name += f" {user.last_name}"
            time_str = datetime.now(TIMEZONE).strftime("%H:%M")
            await callback_query.message.answer(f"Результаты обновил(а) {name} в {time_str}.")

        # Через секунду показываем главное меню
        await asyncio.sleep(1)
        if callback_query.message.chat.type == 'supergroup':
            await self.post_group_menu_buttons(callback_query.message.chat.id)
        else:
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
        await self.dp.start_polling(self.bot)

    async def post_main_menu_buttons(self, chat_id):
        markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Получить результаты", callback_data="get_results"),
             types.InlineKeyboardButton(text="Сгруппированный результат", callback_data="get_group_results")
             ],
        ])

        await self.bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

    async def post_group_menu_buttons(self, chat_id):
        markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Обновить результаты", callback_data="get_group_results")]
        ])
        await self.bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

async def shutdown(bot: TelegramBot):  # pragma: no cover
    await bot.bot.close()

if __name__ == "__main__":  # pragma: no cover
    bot = TelegramBot()

    async def main():
        await bot.bot.set_my_commands([])  

        await bot.start_poll_scheduler(CHAT_ID)
        await bot.dp.start_polling(bot.bot)

    import asyncio
    asyncio.run(main())
   