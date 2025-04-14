import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

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

reply_keyboard = [
    [KeyboardButton(text="Поездки")],
    [KeyboardButton(text="Планирование")],
    [KeyboardButton(text="Заметки")]
]
kb = ReplyKeyboardMarkup(keyboard=reply_keyboard, resize_keyboard=True, one_time_keyboard=False)

# Хранилище состояния ожидания ввода задачи у пользователя
user_states = {}


def get_user_tasks(user_id):
    cursor.execute('SELECT id, task FROM daily_tasks WHERE user_id = ?', (user_id,))
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
    if not tasks:
        await message.reply("У вас пока нет ежедневных дел. Отправьте мне задачу, чтобы добавить её.", reply_markup=kb)
        user_states[user_id] = 'awaiting_task'
        return

    date = get_today_date()
    text = "Ваши ежедневные дела на сегодня:\n"
    for i, (task_id, task_text) in enumerate(tasks, 1):
        done = get_task_status(user_id, task_id, date)
        status = "✅" if done else "❌"
        text += f"{i}. {task_text} {status}\n"
    text += "\nЧтобы отметить задачу выполненной, отправьте её номер.\nЧтобы добавить новую задачу, отправьте текст задачи."
    await message.reply(text, reply_markup=kb)
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
        await message.reply("Вы успешно зарегистрированы!", reply_markup=kb)
    else:
        await message.reply("Вы уже зарегистрированы.", reply_markup=kb)


@dp.message(Command('help'))
async def help_command(message: types.Message):
    await message.reply("Выберите опцию:", reply_markup=kb)


@dp.message()
async def handle_buttons(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()

    # Проверяю состояние пользователя
    state = user_states.get(user_id)

    if state == 'awaiting_task':
        # Добавляю новую задачу
        if text in ["Поездки", "Планирование", "Заметки"]:
            await message.reply("Пожалуйста, сначала добавьте задачу или отмените действие.", reply_markup=kb)
            return
        try:
            cursor.execute('INSERT INTO daily_tasks (user_id, task) VALUES (?, ?)', (user_id, text))
            conn.commit()
            await message.reply(f"Задача '{text}' добавлена!", reply_markup=kb)
            user_states.pop(user_id)
        except sqlite3.IntegrityError:
            await message.reply("Такая задача уже есть.", reply_markup=kb)
        return

    if text == "Планирование":
        await send_tasks_with_status(message)
        return

    if state == 'awaiting_action':
        tasks = get_user_tasks(user_id)
        if text.isdigit():
            num = int(text)
            if 1 <= num <= len(tasks):
                task_id = tasks[num-1][0]
                date = get_today_date()
                done = get_task_status(user_id, task_id, date)
                if done:
                    await message.reply("Эта задача уже отмечена как выполненная.", reply_markup=kb)
                else:
                    set_task_status(user_id, task_id, date, 1)
                    await message.reply(f"Задача '{tasks[num-1][1]}' отмечена как выполненная!", reply_markup=kb)
                return
            else:
                await message.reply("Неверный номер задачи.", reply_markup=kb)
                return
        else:
            # Добавляю новую задачу
            try:
                cursor.execute('INSERT INTO daily_tasks (user_id, task) VALUES (?, ?)', (user_id, text))
                conn.commit()
                await message.reply(f"Задача '{text}' добавлена!", reply_markup=kb)
            except sqlite3.IntegrityError:
                await message.reply("Такая задача уже есть.", reply_markup=kb)
            return

    # Обработка других кнопок
    if text == "Поездки":
        await message.reply("Здесь будет информация о поездках.", reply_markup=kb)
    elif text == "Заметки":
        await message.reply("Здесь будут ваши заметки.", reply_markup=kb)
    else:
        await message.reply("Пожалуйста, используйте клавиатуру для выбора опций.", reply_markup=kb)

async def reminder_task(bot: Bot):
    while True:
        now = datetime.now()
        date = now.strftime('%Y-%m-%d')

        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()

        for (user_id,) in users:
            tasks = get_user_tasks(user_id)
            if not tasks:
                continue

            # Проверяю, все ли задачи выполнены
            all_done = True
            unfinished_tasks = []
            for task_id, task_text in tasks:
                done = get_task_status(user_id, task_id, date)
                if not done:
                    all_done = False
                    unfinished_tasks.append(task_text)

            try:
                if all_done and tasks:
                    await bot.send_message(user_id, "Поздравляем! Все ваши ежедневные дела выполнены! 🎉")
                elif unfinished_tasks:
                    text = "Напоминание: у вас есть невыполненные ежедневные дела:\n"
                    for t in unfinished_tasks:
                        text += f"• {t}\n"
                    await bot.send_message(user_id, text)
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

        # Сбрасываю статусы в полночь
        if now.time() >= time(0, 0) and now.time() < time(0, 10):
            # Удаляю статусы за предыдущий день, чтобы начать заново
            cursor.execute('DELETE FROM daily_tasks_status WHERE date != ?', (date,))
            conn.commit()

        #  2 часа
        await asyncio.sleep(2 * 60 * 60)

if __name__ == '__main__':
    import asyncio
    from aiogram import Bot

    bot = Bot(token=BOT_TOKEN)
    dp.run_polling(bot)

