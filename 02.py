import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

from config import BOT_TOKEN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

dp = Dispatcher()

# Создаю и подключаюсь к базе данных
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Создаю таблицу пользователей, если она не существует
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT
)
''')
conn.commit()

async def main():
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)

@dp.message(Command('start'))
async def start(message: types.Message):
    user_id = message.from_user.id

    # Проверяю, есть ли пользователь в базе
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()

    if user is None:
        # Если пользователя нет — добавляю
        cursor.execute(
            'INSERT INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)',
            (
                user_id,
                message.from_user.username,
                message.from_user.first_name,
                message.from_user.last_name
            )
        )
        conn.commit()
        await message.reply("Вы успешно зарегистрированы!")
    else:
        await message.reply("Вы уже зарегистрированы.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        conn.close()

