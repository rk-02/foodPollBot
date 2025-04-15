import asyncio
import signal
from datetime import datetime, timedelta

import pandas as pd
from telegram import Update, Bot, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError  # Если нужно обрабатывать FloodWait
from telethon.errors import (
    SessionPasswordNeededError,
    RPCError,
)  # Общие ошибки Telethon
import pytz
import json



# Конфигурация
BOT_TOKEN = "7672011364:AAE8BjuFYq6YN6CRlj2MiY6yY6tAKJWoZIA"
CHAT_ID = -1002391359004
TIMEZONE = pytz.timezone('Asia/Yekaterinburg')
POLL_START = {'hour': 13, 'minutes': 39}
REMIND_START = {'hour': 20, 'minutes': 00}
POLL_SHIFT = 1
API_HASH = 'fc2925c0f23d660b14e5bd00d36efa95'
API_ID = 11609594

with open("schedule.json", "r", encoding="utf-8") as file:
    POLLS = json.load(file)

class PollBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.running = True
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.current_poll_message_id = None
        self.last_polls = []
        self.last_bot_message_id = None
        self.user_message_ids = {}

    async def delete_user_messages(self, chat_id, user_id):
        """Удаляет только сообщения общения с ботом"""
        if user_id in self.user_message_ids.get(chat_id, {}):
            for msg_id in self.user_message_ids[chat_id][user_id]:
                try:
                    await self.bot.delete_message(
                        chat_id=chat_id,
                        message_id=msg_id
                    )
                except Exception as e:
                    print(f"Не удалось удалить сообщение пользователя: {e}")
            # Очищаем только обработанные сообщения
            self.user_message_ids[chat_id][user_id] = []

    async def track_user_message(self, chat_id, user_id, message_id):
        """Отслеживает сообщение пользователя для последующего удаления"""
        if chat_id not in self.user_message_ids:
            self.user_message_ids[chat_id] = {}
        if user_id not in self.user_message_ids[chat_id]:
            self.user_message_ids[chat_id][user_id] = []
        # Добавляем только команды бота и ответы на них
        if len(self.user_message_ids[chat_id][user_id]) == 0 or \
        message_id > self.user_message_ids[chat_id][user_id][-1]:
            self.user_message_ids[chat_id][user_id].append(message_id)

    async def delete_previous_message(self, chat_id):
        """Удаляет предыдущее сообщение бота"""
        if self.last_bot_message_id:
            try:
                await self.bot.delete_message(
                    chat_id=chat_id,
                    message_id=self.last_bot_message_id
                )
            except Exception as e:
                print(f"Не удалось удалить сообщение бота: {e}")
            self.last_bot_message_id = None

    async def send_message_with_delete(self, chat_id, text, reply_markup=None, parse_mode=None):
        """Отправляет сообщение, предварительно удаляя предыдущее"""
        await self.delete_previous_message(chat_id)
        message = await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        self.last_bot_message_id = message.message_id
        return message

    async def safe_delete_message(self, chat_id, message_id):
        """Безопасное удаление сообщения с обработкой ошибок"""
        try:
            await self.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id
            )
            return True
        except Exception as e:
            print(f"Не удалось удалить сообщение {message_id}: {e}")
            return False

    async def send_scheduled_polls(self):
        while self.running:
            now = datetime.now(TIMEZONE)

            #if(now.weekday() + POLL_SHIFT == 5 or now.weekday() + POLL_SHIFT == 6):
            #    await asyncio.sleep(30)
            #    continue

            if now.hour == POLL_START['hour'] and now.minute == POLL_START['minutes']: 
                poll_number = (now.weekday() + POLL_SHIFT) % 7

                next_poll_date = now + timedelta(days=POLL_SHIFT)

                day_of_month = next_poll_date.day
                month = next_poll_date.month
                #formatted_date = f"{day_of_month:02d}.{month:02d}"
                formatted_date = f"14.04"

                for poll_data in POLLS[1]:
                    try:
                        #await self.delete_previous_message(CHAT_ID)
                        
                        if len(poll_data["options"]) == 1:
                            poll_data["options"].append("-")

                        poll_message = await self.bot.send_poll(
                            chat_id=CHAT_ID,
                            question=poll_data["question"] + ' ' + formatted_date,
                            options=poll_data["options"],
                            is_anonymous=poll_data["is_anonymous"]
                        )
                        self.current_poll_message_id = poll_message.message_id
                        poll_key = poll_data["question"]  # Используем вопрос как ключ
                        self.last_polls[poll_key] = {
                            "message_id": poll_message.message_id,
                            "question": poll_data["question"] + ' ' + formatted_date,
                            "options": poll_data["options"]
                        }
                        if len(self.last_polls) > num_of_polls:
                            self.last_polls = self.last_polls[:num_of_polls]
                        await asyncio.sleep(1)
                    except Exception as e:
                        print(f"Ошибка при отправке опроса: {e}")
                        
                await asyncio.sleep(60)
            await asyncio.sleep(30)

            # Отправка напоминания в 12:00
            if now.hour == REMIND_START['hour'] and now.minute == REMIND_START['minutes']:
                try:
                    await self.bot.send_message(
                        chat_id=CHAT_ID,
                        text="📢 Проходим опрос, кто не проголосовал!"
                    )
                except Exception as e:
                    print(f"Ошибка при отправке напоминания: {e}")
                await asyncio.sleep(60)  # Ждем минуту, чтобы избежать повторной отправки

            # Проверяем каждые 30 секунд
            await asyncio.sleep(30)

    async def get_poll_results(self):
        """
        Получает результаты последних опросов и возвращает их в виде DataFrame.
        В случае ошибки возвращает пустой DataFrame и логирует ошибку.
        """

        client = TelegramClient('user_session', API_ID, API_HASH)

        channel = await client.get_entity(CHAT_ID)

        self.bot.send_message(
            chat_id=CHAT_ID,
            text='channel'
        )

        return
        
        try:
            # Подключаемся к клиенту
            await client.start(phone=PHONE)
            channel = await client.get_entity(CHAT_ID)

            # Получаем последние опросы
            polls = []
            for poll_data in self.last_polls.values():
                try:
                    msg = await client.get_messages(CHAT_ID, ids=poll_data["message_id"])
                    if msg and msg.media and hasattr(msg.media, 'poll'):
                        polls.append(msg)
                except:
                    continue

            # Формируем данные для вывода
            excel_data = []
            for poll_msg in polls:
                poll = poll_msg.media.poll
                results = poll_msg.media.results

                # Форматируем вопрос
                question = (poll.question.text if hasattr(poll.question, 'text') 
                        else str(poll.question))
                
                # Обрабатываем варианты ответов
                for answer in poll.answers:
                    answer_text = answer.text if hasattr(answer, 'text') else str(answer)
                    
                    # Получаем количество голосов
                    votes = 0
                    if results and results.results:
                        for r in results.results:
                            if r.option == answer.option:
                                votes = r.voters
                                break

                    if votes > 0:  # Игнорируем варианты без голосов
                        excel_data.append({
                            "Вопрос": question,
                            "Вариант ответа": answer_text,
                            "Голосов": votes,
                            "Дата опроса": poll_msg.date.strftime("%d.%m.%Y %H:%M")
                        })

            # Формируем DataFrame
            df = pd.DataFrame(excel_data)
            
            # Форматируем вывод для Telegram
            if not df.empty:
                # Группируем по вопросам
                grouped = df.groupby('Вопрос')
                
                output = []
                for question, group in grouped:
                    # Заголовок вопроса
                    output.append(f"*{question}*")
                    
                    # Варианты ответов
                    for _, row in group.iterrows():
                        option = row['Вариант ответа'].text
                        votes = row['Голосов']
                        date = row['Дата опроса']
                        
                        output.append(
                            f"`{option}` - {votes} гол.\n"
                        )
                    
                    output.append("")  # Пустая строка между вопросами
                return "\n".join(output), df
            return "❌ Нет данных по опросам", pd.DataFrame()

        except Exception as e:
            error_msg = f"❌ *Ошибка:*\n```{str(e)}```"
            return error_msg, pd.DataFrame()
            
        finally:
            await client.disconnect()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.delete_user_messages(update.message.chat_id, update.message.from_user.id)
        await self.track_user_message(update.message.chat_id, update.message.from_user.id, update.message.message_id)
        
        keyboard = [["📊 Получить результаты", "📝 Редактировать опрос"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await self.send_message_with_delete(
            chat_id=update.message.chat_id,
            text="Выберите действие:",
            reply_markup=reply_markup
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Проверяем, является ли сообщение командой для бота
        if not (update.message.text.startswith("/") or 
                update.message.text in ["📊 Получить результаты", "📝 Редактировать опрос"] or
                context.user_data.get("poll_edit_stage")):
            return  # Игнорируем остальные сообщения

        await self.delete_user_messages(update.message.chat_id, update.message.from_user.id)
        await self.track_user_message(update.message.chat_id, update.message.from_user.id, update.message.message_id)
        
        text = update.message.text

        if text == "📊 Получить результаты":
            user_message_id = update.message.message_id

            await self.send_message_with_delete(
                chat_id=update.message.chat_id,
                text="⏳ Загружаю результаты..."
            )
            telegram_text, df = await self.get_poll_results()

            await self.send_message_with_delete(
                chat_id=update.message.chat_id,
                text='Функция пока кривая'
            )

            keyboard = [["📊 Получить результаты", "📝 Редактировать опрос"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            message = await self.bot.send_message(
                chat_id=update.message.chat_id,
                text="Выберите действие",
                reply_markup=reply_markup
            )
            self.last_bot_message_id = message.message_id

            return
            
            if isinstance(df, pd.DataFrame) and not df.empty:
                # Отправляем форматированный текст в Telegram
                await self.send_message_with_delete(
                    chat_id=update.message.chat_id,
                    text=f"📊 *Результаты опросов:*\n\n {telegram_text}",
                    parse_mode="Markdown"
                )

                # Отправляем Excel-файл
                #file_name = "poll_results.xlsx"
                #df.to_excel(file_name, index=False)
                #with open(file_name, "rb") as file:
                #    await context.bot.send_document(
                #        chat_id=update.message.chat_id,
                #        document=file,
                #        caption="Полные данные в Excel"
                #    )
            else:
                await self.send_message_with_delete(
                    chat_id=update.message.chat_id,
                    text=telegram_text  # Здесь будет сообщение об ошибке или "Нет данных"
                )

            #await self.safe_delete_message(update.message.chat_id, user_message_id)
            
            keyboard = [["📊 Получить результаты", "📝 Редактировать опрос"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            message = await self.bot.send_message(
                chat_id=update.message.chat_id,
                text="Выберите действие",
                reply_markup=reply_markup
            )
            self.last_bot_message_id = message.message_id

        elif text == "📝 Редактировать опрос":
            if not self.last_polls:
                await self.send_message_with_delete(
                    chat_id=update.message.chat_id,
                    text="Нет доступных опросов для редактирования."
                )

                keyboard = [["📊 Получить результаты", "📝 Редактировать опрос"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await self.send_message_with_delete(
                    chat_id=update.message.chat_id,
                    text="Выберите действие",
                    reply_markup=reply_markup
                )

                return

            keyboard = []
            for i, poll in enumerate(self.last_polls, 1):
                keyboard.append([f"{i}. {poll['question'][:30]}..."])
            
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await self.send_message_with_delete(
                chat_id=update.message.chat_id,
                text="Выберите опрос для редактирования:",
                reply_markup=reply_markup
            )
            context.user_data["poll_edit_stage"] = "select_poll"

        elif context.user_data.get("poll_edit_stage") == "select_poll":
            try:
                print(self.last_polls)
                selected_index = int(text.split(".")[0]) - 1
                if 0 <= selected_index < len(self.last_polls):
                    selected_poll = self.last_polls[selected_index]
                    context.user_data["selected_poll"] = selected_poll
                    context.user_data["poll_edit_stage"] = "enter_options"
                    
                    await self.send_message_with_delete(
                        chat_id=update.message.chat_id,
                        text=f"Выбран опрос: {selected_poll['question']}\n"
                             "Введите новые варианты ответов через запятую:",
                        reply_markup=ReplyKeyboardMarkup([["Отменить"]], resize_keyboard=True)
                    )
                else:
                    await self.send_message_with_delete(
                        chat_id=update.message.chat_id,
                        text="Неверный выбор. Попробуйте еще раз."
                    )
            except (ValueError, IndexError):
                await self.send_message_with_delete(
                    chat_id=update.message.chat_id,
                    text="Пожалуйста, выберите опрос из списка."
                )

        elif context.user_data.get("poll_edit_stage") == "enter_options":
            if text.lower() == "отменить":
                await self.cancel_edit(update, context)
                return

            new_options = [opt.strip() for opt in text.split(",") if opt.strip()]
            if not new_options:
                await self.send_message_with_delete(
                    chat_id=update.message.chat_id,
                    text="Вы не ввели варианты ответов. Попробуйте еще раз."
                )
                return

            context.user_data["new_options"] = new_options
            context.user_data["poll_edit_stage"] = "confirm"
            
            confirm_keyboard = [["✅ Подтвердить", "❌ Отменить"]]
            reply_markup = ReplyKeyboardMarkup(confirm_keyboard, resize_keyboard=True)
            
            options_text = "\n".join(f"• {opt}" for opt in new_options)
            await self.send_message_with_delete(
                chat_id=update.message.chat_id,
                text=f"Новые варианты ответов:\n{options_text}\n\nПодтвердите изменение опроса:",
                reply_markup=reply_markup
            )

        elif context.user_data.get("poll_edit_stage") == "confirm":
            # Удаляем сообщение пользователя с кнопками подтверждения
            await self.safe_delete_message(update.message.chat_id, update.message.message_id)

            if text == "✅ Подтвердить":
                selected_poll = context.user_data["selected_poll"]
                new_options = context.user_data["new_options"]
                
                # 1. Удаляем старую версию
                poll_key = selected_poll["question"].split(' ')[0]  # Извлекаем базовый вопрос
                if poll_key in self.last_polls:
                    del self.last_polls[poll_key]
                
                # 2. Создаём новый опрос
                new_poll = await self.bot.send_poll(...)
                
                # 3. Сохраняем только новую версию
                self.last_polls[poll_key] = {
                    "message_id": new_poll.message_id,
                    "question": selected_poll["question"],
                    "options": new_options
                }
                
                try:
                    await self.bot.send_poll(
                        chat_id=CHAT_ID,
                        question=selected_poll["question"],
                        options=new_options,
                        is_anonymous=False
                    )
                    await self.send_message_with_delete(
                        chat_id=update.message.chat_id,
                        text="Опрос был обновлен, пожалуйста, пройдите заново"
                    )
                    
                    try:
                        await self.bot.delete_message(
                            chat_id=CHAT_ID,
                            message_id=selected_poll["message_id"]
                        )
                    except Exception as e:
                        print(f"Не удалось удалить старый опрос: {e}")

                    keyboard = [["📊 Получить результаты", "📝 Редактировать опрос"]]
                    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                    await self.send_message_with_delete(
                        chat_id=update.message.chat_id,
                        text="Опрос успешно обновлен! Выберите следующее действие:",
                        reply_markup=reply_markup
                    )
                    
                except Exception as e:
                    await self.send_message_with_delete(
                        chat_id=update.message.chat_id,
                        text=f"Ошибка при обновлении опроса: {e}"
                    )
                
                await self.cancel_edit(update, context)
                
            elif text == "❌ Отменить":
                await self.cancel_edit(update, context)
            else:
                await self.send_message_with_delete(
                    chat_id=update.message.chat_id,
                    text="Пожалуйста, подтвердите или отмените изменение."
                )

    async def cancel_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Удаляем сообщение пользователя с кнопками подтверждения/отмены
        await self.safe_delete_message(update.message.chat_id, update.message.message_id)

        if "poll_edit_stage" in context.user_data:
            del context.user_data["poll_edit_stage"]
        if "selected_poll" in context.user_data:
            del context.user_data["selected_poll"]
        if "new_options" in context.user_data:
            del context.user_data["new_options"]
        
        keyboard = [["📊 Получить результаты", "📝 Редактировать опрос"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await self.send_message_with_delete(
            chat_id=update.message.chat_id,
            text="Выберите действие",
            reply_markup=reply_markup
        )

    async def run(self):
        try:
            await self.application.initialize()
            self.application.add_handler(CommandHandler("start", self.start))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

            asyncio.create_task(self.send_scheduled_polls())

            await self.application.start()
            await self.application.updater.start_polling()

            while self.running:
                await asyncio.sleep(1)

        except Conflict as e:
            print("❗ Конфликт: Убедитесь, что запущен только один экземпляр бота.")
        except Exception as e:
            print(f"❌ Неизвестная ошибка: {e}")
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

def signal_handler(signum, frame, bot):
    print("\nПолучен сигнал завершения (Ctrl+C). Останавливаю бота...")
    bot.running = False

if __name__ == "__main__":
    bot = PollBot()
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, bot))
    asyncio.run(bot.run())