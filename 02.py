import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from config import BOT_TOKEN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

dp = Dispatcher()

conn = sqlite3.connect('users.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT
)
''')
conn.commit()

reply_keyboard = [
    [KeyboardButton(text="Поездки")],
    [KeyboardButton(text="Планирование")],
    [KeyboardButton(text="Заметки")]
]
kb = ReplyKeyboardMarkup(keyboard=reply_keyboard, resize_keyboard=True, one_time_keyboard=False)

async def main():
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)

@dp.message(Command('start'))
async def start(message: types.Message):
    user_id = message.from_user.id

    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()

    if user is None:
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
        await message.reply("Вы успешно зарегистрированы!", reply_markup=kb)
    else:
        await message.reply("Вы уже зарегистрированы.", reply_markup=kb)

@dp.message(Command('help'))
async def help_command(message: types.Message):
    await message.reply("Выберите опцию:", reply_markup=kb)

@dp.message()
async def handle_buttons(message: types.Message):
    text = message.text
    if text == "Поездки":
        await message.reply("Здесь будет информация о поездках.", reply_markup=kb)
    elif text == "Планирование":
        await message.reply("Здесь будет информация о планировании.", reply_markup=kb)
    elif text == "Заметки":
        await message.reply("Здесь будут ваши заметки.", reply_markup=kb)
    else:
        await message.reply("Пожалуйста, используйте кнопки меню. Введите /help для отображения меню.", reply_markup=kb)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        conn.close()

