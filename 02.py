import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from config import BOT_TOKEN

# делаю защиту против рекламы и т.д
import requests

TOKEN = '7585920451:AAFr1eFDKgH37GoqztPry9uw0XHWUTcVCrM'
url = f'https://api.telegram.org/bot{TOKEN}/deleteWebhook'
response = requests.get(url)
print(response.json())

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

cursor.execute('''
CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    destination TEXT,
    date TEXT,
    time TEXT,
    address TEXT,
    created_at TEXT
)
''')
conn.commit()

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
        [KeyboardButton(text="Посмотреть список дел")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Хранилище состояния ожидания ввода задачи у пользователя
user_states = {}
trip_states = {}


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

    # Обработка основных команд вне зависимости от состояния
    if text == "Планирование":
        user_states[user_id] = None  # Сброс состояния
        await message.reply("Вы выбрали 'Планирование'.", reply_markup=planning_keyboard)
        return

    elif text == "Поездки":
        trip_states[user_id] = {'step': 'awaiting_date', 'data': {}}
        await message.reply("Введите дату поездки в формате ГГГГ-ММ-ДД (например, 2024-06-15):",
                            reply_markup=main_keyboard)
        return


    elif text == "Заметки":
        user_states[user_id] = 'awaiting_task'
        await message.reply("Вы выбрали 'Заметки'. Пожалуйста, добавьте задачу.", reply_markup=main_keyboard)
        return

    # Обработка состояний
    state = user_states.get(user_id)

    if state == 'awaiting_task':
        try:
            today_date = get_today_date()
            cursor.execute('INSERT INTO daily_tasks (user_id, task, date) VALUES (?, ?, ?)',
                           (user_id, text, today_date))
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
                user_states.pop(user_id)
            else:
                await message.reply("Неверный номер задачи. Пожалуйста, попробуйте снова.", reply_markup=main_keyboard)
        except ValueError:
            await message.reply("Пожалуйста, введите номер задачи.", reply_markup=main_keyboard)
        return

    # Обработка кнопок из клавиатуры "Планирование"
    if text == "Добавить задачу":
        user_states[user_id] = 'awaiting_task'
        await message.reply("Пожалуйста, введите текст задачи:", reply_markup=main_keyboard)
        return

    elif text.lower() == "посмотреть список дел":
        await send_tasks_with_status(message)
        user_states[user_id] = 'awaiting_action'
        return

    #  Обработка  ввода поездки
    if user_id in trip_states:
        state = trip_states[user_id]
        step = state['step']
        data = state['data']

        if step == 'awaiting_date':
            try:
                datetime.strptime(text, '%Y-%m-%d')
                data['date'] = text
                state['step'] = 'awaiting_time'
                await message.reply("Введите время поездки в формате ЧЧ:ММ (например, 14:30):")
            except ValueError:
                await message.reply("Неверный формат даты. Попробуйте снова (ГГГГ-ММ-ДД).")
            return

        elif step == 'awaiting_time':
            try:
                datetime.strptime(text, '%H:%M')
                data['time'] = text
                state['step'] = 'awaiting_address'
                await message.reply("Введите адрес или место назначения:")
            except ValueError:
                await message.reply("Неверный формат времени. Попробуйте снова (ЧЧ:ММ).")
            return

        elif step == 'awaiting_address':
            data['address'] = text
            data['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Сохраняю поездку
            cursor.execute('''
                    INSERT INTO trips (user_id, destination, date, time, address, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, text, data['date'], data['time'], data['address'], data['created_at']))
            conn.commit()

            # Удаляю состояние
            trip_states.pop(user_id)

            # Формирую ссылку на карту
            map_url = f"https://yandex.ru/maps/?text={text.replace(' ', '+')}"

            await message.reply(
                f"🚗 Поездка добавлена!\n📅 Дата: {data['date']}\n⏰ Время: {data['time']}\n📍 Адрес: {data['address']}\n\n"
                f"🗺 Открыть на карте: {map_url}",
                reply_markup=main_keyboard
            )
            return


async def reminder_loop(bot: Bot):
    while True:
        await asyncio.sleep(60 * 10)  # Проверяю каждые 10 минут

        now = datetime.now()
        today = get_today_date()

        # Напоминания о невыполненных задачах
        cursor.execute("SELECT DISTINCT user_id FROM daily_tasks WHERE date = ?", (today,))
        users = cursor.fetchall()

        for (user_id,) in users:
            tasks = get_user_tasks(user_id)
            for task_id, task_text in tasks:
                status = get_task_status(user_id, task_id, today)
                if status == 0:
                    try:
                        await bot.send_message(
                            user_id,
                            "🔔 У вас есть невыполненные задачи на сегодня. Не забудьте их завершить!",
                            reply_markup=main_keyboard
                        )
                        break  # Отправляю только одно напоминание
                    except Exception as e:
                        logging.warning(f"Не удалось отправить сообщение пользователю {user_id}: {e}")


if __name__ == '__main__':
    bot = Bot(token=BOT_TOKEN)


    async def main():
        # Запускаю фоновую задачу
        asyncio.create_task(reminder_loop(bot))
        # Запускаю бота
        await dp.start_polling(bot)


    asyncio.run(main())
