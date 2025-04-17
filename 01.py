import logging
import sqlite3
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

API_TOKEN = 'YOUR_API_TOKEN_HERE'  # Замените на ваш токен

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)  # Передаем экземпляр бота в диспетчер

# Подключение к базе данных
conn = sqlite3.connect('task.db')
cursor = conn.cursor()

# Создание таблиц, если они не существуют
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS daily_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task TEXT,
    UNIQUE(user_id, task)
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS daily_tasks_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task_id INTEGER,
    date TEXT,
    done INTEGER DEFAULT 0,
    UNIQUE(user_id, task_id, date)
)
''')
conn.commit()

# Клавиатура
reply_keyboard = [
    [KeyboardButton(text="Планирование")],
    [KeyboardButton(text="Заметки")]
]
kb = ReplyKeyboardMarkup(keyboard=reply_keyboard, resize_keyboard=True)

# Хранилище состояния ожидания ввода задачи у пользователя
user_states = {}

# Определение функций, которые вы уже написали...

async def main():
    await dp.start_polling()

if __name__ == '__main__':
    asyncio.run(main())
