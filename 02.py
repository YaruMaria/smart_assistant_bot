import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from config import BOT_TOKEN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

dp = Dispatcher()

conn = sqlite3.connect('user.db')
cursor = conn.cursor()

# Создание таблиц, если они не существуют
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS daily_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task TEXT,
    date TEXT,
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

# Основная клавиатура
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Поездки")],
        [KeyboardButton(text="Планирование")],
        [KeyboardButton(text="Заметки")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# Клавиатура для планирования
planning_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Добавить задачу")],
        [KeyboardButton(text="Посмотреть  список дел")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Хранилище состояния ожидания ввода задачи у пользователя
user_states = {}

def get_user_tasks(user_id):
    cursor.execute('SELECT id, task FROM daily_tasks WHERE user_id = ? AND date = ?', (user_id, get_today_date()))
    return cursor.fetchall()

def get_today_date():
    return datetime.now().strftime('%Y-%m-%d')

def get_task_status(user_id, task_id, date):
    cursor.execute('SELECT done FROM daily_tasks_status WHERE user_id = ? AND task_id = ? AND date = ?',
                   (user_id, task_id, date))
    row = cursor.fetchone()
    if row:
        return row[0]
    return 0

def set_task_status(user_id, task_id, date, done):
    try:
        cursor.execute('INSERT INTO daily_tasks_status (user_id, task_id, date, done) VALUES (?, ?, ?, ?)',
                       (user_id, task_id, date, done))
    except sqlite3.IntegrityError:
        cursor.execute('UPDATE daily_tasks_status SET done = ? WHERE user_id = ? AND task_id = ? AND date = ?',
                       (done, user_id, task_id, date))
    conn.commit()

async def send_tasks_with_status(message: types.Message):
    user_id = message.from_user.id
    tasks = get_user_tasks(user_id)
    date = get_today_date()  # Получаю текущую дату
    today_tasks = []

    for task in tasks:
        task_id, task_text = task
        done = get_task_status(user_id, task_id, date)
        today_tasks.append((task_id, task_text, done))

    if not today_tasks:
        await message.reply(
            "У вас пока нет ежедневных дел на сегодня. Пожалуйста, добавьте задачу, отправив текст задачи.",
            reply_markup=main_keyboard
        )
        user_states[user_id] = 'awaiting_task'
        return

    text = "Ваши ежедневные дела на сегодня:\n"
    for i, (task_id, task_text, done) in enumerate(today_tasks, 1):
        status = "✅" if done else "❌"
        text += f"{i}. {task_text} {status}\n"
    text += "\nЧтобы отметить задачу выполненной, отправьте её номер.\nЧтобы добавить новую задачу, отправьте текст задачи."
    await message.reply(text, reply_markup=main_keyboard)
    user_states[user_id] = 'awaiting_action'

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
        await message.reply("Вы успешно зарегистрированы!", reply_markup=main_keyboard)
    else:
        await message.reply("Вы уже зарегистрированы.", reply_markup=main_keyboard)

@dp.message(Command('help'))
async def help_command(message: types.Message):
    await message.reply("Выберите опцию:", reply_markup=main_keyboard)

@dp.message()
async def handle_buttons(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    logging.info(f"Received message: {text} from user: {user_id}")

    # Проверка состояния пользователя
    state = user_states.get(user_id)

    if state == 'awaiting_task':
        # Добавление новой задачи
        if text in ["Поездки", "Планирование", "Заметки"]:
            await message.reply("Пожалуйста, сначала добавьте задачу или отмените действие.", reply_markup=main_keyboard)
            return
        try:
            today_date = get_today_date()  # Получаю текущую дату
            cursor.execute('INSERT INTO daily_tasks (user_id, task, date) VALUES (?, ?, ?)', (user_id, text, today_date))
            conn.commit()
            await message.reply(f"Задача '{text}' добавлена!", reply_markup=main_keyboard)
            user_states.pop(user_id)
        except sqlite3.IntegrityError:
            await message.reply("Такая задача уже есть.", reply_markup=main_keyboard)
        return

    elif state == 'awaiting_action':
        try:
            task_index = int(text) - 1
            tasks = get_user_tasks(user_id)
            if 0 <= task_index < len(tasks):
                task_id, task_text = tasks[task_index]
                today_date = get_today_date()
                current_status = get_task_status(user_id, task_id, today_date)
                new_status = 1 if current_status == 0 else 0
                set_task_status(user_id, task_id, today_date, new_status)
                status_text = "выполнена" if new_status == 1 else "не выполнена"
                await message.reply(f"Задача '{task_text}' отмечена как {status_text}.", reply_markup=main_keyboard)
            else:
                await message.reply("Неверный номер задачи. Пожалуйста, попробуйте снова.", reply_markup=main_keyboard)
        except ValueError:
            await message.reply("Пожалуйста, введите номер задачи.", reply_markup=main_keyboard)
        return

    # Обработка кнопок
    if text == "Поездки":
        await message.reply("Вы выбрали 'Поездки'. Пожалуйста, добавьте задачу.", reply_markup=main_keyboard)
        user_states[user_id] = 'awaiting_task'
        return

    elif text == "Планирование":
        await message.reply("Вы выбрали 'Планирование'.", reply_markup=planning_keyboard)
        return

    elif text == "Заметки":
        await message.reply("Вы выбрали 'Заметки'. Пожалуйста, добавьте задачу.", reply_markup=main_keyboard)
        user_states[user_id] = 'awaiting_task'
        return

    elif text == "Добавить задачу":
        await message.reply("Пожалуйста, введите текст задачи:", reply_markup=main_keyboard)
        user_states[user_id] = 'awaiting_task'
        return

    elif text == "Посмотреть список дел":
        await send_tasks_with_status(message)
        return

    else:
        await send_tasks_with_status(message)

if __name__ == '__main__':
    bot = Bot(token=BOT_TOKEN)
    dp.run_polling(bot)

