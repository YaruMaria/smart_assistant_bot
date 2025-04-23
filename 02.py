import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from stic import cmd_start as stic_start, photo_handler as stic_photo_handler, caption_handler as stic_caption_handler, \
    user_data
from stic import user_data as stic_user_data

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
);
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS daily_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task TEXT,
    date TEXT,
    priority INTEGER DEFAULT 3,  -- 1: высокая, 2: средняя, 3: низкая
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
);
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
);
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS user_achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    badge_name TEXT,
    badge_description TEXT,
    achieved_at TEXT,
    UNIQUE(user_id, badge_name)
);
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS user_stats (
    user_id INTEGER PRIMARY KEY,
    tasks_completed INTEGER DEFAULT 0,
    high_priority_completed INTEGER DEFAULT 0,
    streaks INTEGER DEFAULT 0,
    last_completion_date TEXT
);
''')

conn.commit()

# Основная клавиатура
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Поездки")],
        [KeyboardButton(text="Планирование")],
        [KeyboardButton(text="Мои достижения"), KeyboardButton(text="Мой прогресс")],
        [KeyboardButton(text="создать стикер")]
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

trips_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Посмотреть мои поездки")],
        [KeyboardButton(text="Добавить поездку")],
        [KeyboardButton(text="Назад")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

back_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Назад")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Хранилище состояния ожидания ввода задачи у пользователя
user_states = {}
trip_states = {}


def get_task_status(user_id: int, task_id: int, date: str) -> bool:
    # Проверяю статус выполнения задачи
    try:
        cursor.execute('''
            SELECT done FROM daily_tasks_status 
            WHERE user_id = ? AND task_id = ? AND date = ?
        ''', (user_id, task_id, date))
        result = cursor.fetchone()
        return bool(result[0]) if result else False
    except Exception as e:
        logging.error(f"Ошибка при проверке статуса задачи: {e}")
        return False


@dp.message(F.text == "Мой прогресс")
async def show_progress_handler(message: types.Message):
    await show_progress(message)

    check_achievements


@dp.message(F.text == "Мои достижения")
async def show_achievements_handler(message: types.Message):
    await show_achievements(message)


def update_user_stats(user_id: int, priority: int = None):
    # Обновляю статистику пользователя после выполнения задачи
    today = get_today_date()
    cursor.execute('SELECT last_completion_date FROM user_stats WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()

    if result is None:
        # Новый пользователь
        cursor.execute('''
            INSERT INTO user_stats (user_id, tasks_completed, high_priority_completed, streaks, last_completion_date)
            VALUES (?, 1, ?, 1, ?)
        ''', (user_id, 1 if priority == 1 else 0, today))
    else:
        last_date = result[0]
        streaks = 1 if last_date != today else 0

        # Обновляю статистику в зависимости от приоритета
        if priority == 1:
            cursor.execute('''
                UPDATE user_stats 
                SET tasks_completed = tasks_completed + 1,
                    high_priority_completed = high_priority_completed + 1,
                    streaks = streaks + ?,
                    last_completion_date = ?
                WHERE user_id = ?
            ''', (streaks, today, user_id))
        else:
            cursor.execute('''
                UPDATE user_stats 
                SET tasks_completed = tasks_completed + 1,
                    streaks = streaks + ?,
                    last_completion_date = ?
                WHERE user_id = ?
            ''', (streaks, today, user_id))

    conn.commit()


def get_user_tasks(user_id: int) -> list:
    # Получаю список задач пользователя на сегодня
    today_date = get_today_date()
    try:
        cursor.execute('''
            SELECT t.id, t.task, t.priority
            FROM daily_tasks t
            WHERE t.user_id = ? AND t.date = ?
            ORDER BY t.priority ASC
        ''', (user_id, today_date))
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"Ошибка при получении задач пользователя {user_id}: {e}")
        return []


def check_achievements(user_id: int):
    # Проверяю, какие достижения заработал пользователь
    cursor.execute('''
        SELECT tasks_completed, high_priority_completed, streaks 
        FROM user_stats 
        WHERE user_id = ?
    ''', (user_id,))

    stats = cursor.fetchone()

    if not stats:
        return []

    tasks_completed, high_priority_completed, streaks = stats
    new_achievements = []

    #  условия для наград
    achievements = [
        ("Новичок", "Выполнил первую задачу!", lambda: tasks_completed >= 1),
        ("Трудяга", "Выполнил 10 задач!", lambda: tasks_completed >= 10),
        ("Мастер продуктивности", "Выполнил 50 задач!", lambda: tasks_completed >= 50),
        ("Легенда", "Выполнил 100 задач!", lambda: tasks_completed >= 100),
        ("Срочник", "Выполнил 5 задач с высоким приоритетом", lambda: high_priority_completed >= 5),
        ("Герой срочных дел", "Выполнил 20 задач с высоким приоритетом", lambda: high_priority_completed >= 20),
        ("Серийный исполнитель", "Выполнял задачи 3 дня подряд", lambda: streaks >= 3),
        ("Недельный чемпион", "Выполнял задачи 7 дней подряд", lambda: streaks >= 7),
        ("Месяц дисциплины", "Выполнял задачи 30 дней подряд", lambda: streaks >= 30),
        ("Перфекционист", "Выполнил 10 задач подряд без пропусков", lambda: streaks >= 10)
    ]

    for name, desc, condition in achievements:
        # Проверяю, есть ли уже такая награда у пользователя
        cursor.execute('SELECT 1 FROM user_achievements WHERE user_id = ? AND badge_name = ?', (user_id, name))
        if not cursor.fetchone() and condition():
            # Добавляю новую награду
            cursor.execute('''
                INSERT INTO user_achievements (user_id, badge_name, badge_description, achieved_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, name, desc, get_today_date()))
            new_achievements.append((name, desc))

    conn.commit()
    return new_achievements


async def show_achievements(message: types.Message):
    # Показываю все полученные пользователем награды
    user_id = message.from_user.id
    cursor.execute('''
        SELECT badge_name, badge_description, achieved_at 
        FROM user_achievements 
        WHERE user_id = ?
        ORDER BY achieved_at DESC
    ''', (user_id,))

    achievements = cursor.fetchall()

    if not achievements:
        await message.reply("У вас пока нет наград. Выполняйте задачи, чтобы получать их!", reply_markup=main_keyboard)
        return

    text = "🏆 Ваши достижения:\n\n"
    for i, (name, desc, date) in enumerate(achievements, 1):
        text += f"{i}. {name} - {desc}\n   🗓 {date}\n\n"

    await message.reply(text, reply_markup=main_keyboard)


async def send_tasks_with_status(message: types.Message):
    user_id = message.from_user.id
    tasks = get_user_tasks(user_id)
    today_date = get_today_date()

    if not tasks:
        await message.reply(
            "У вас пока нет ежедневных дел на сегодня. Пожалуйста, добавьте задачу, отправив текст задачи.",
            reply_markup=main_keyboard
        )
        return

    text = "📝 Ваши ежедневные дела на сегодня:\n\n"
    for i, (task_id, task_text, priority) in enumerate(tasks, 1):
        done = get_task_status(user_id, task_id, today_date)
        status = "✅" if done else "❌"
        priority_icon = "🔴" if priority == 1 else "🟡" if priority == 2 else "🟢"
        text += f"{i}. {priority_icon} {task_text} {status}\n"

    text += "\nЧтобы отметить задачу выполненной, отправьте её номер."
    await message.reply(text, reply_markup=main_keyboard)
    user_states[user_id] = 'awaiting_action'


async def ask_task_priority(message: types.Message, task_text: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔴 Высокая", callback_data=f"set_priority:{task_text}:1"),
            InlineKeyboardButton(text="🟡 Средняя", callback_data=f"set_priority:{task_text}:2"),
            InlineKeyboardButton(text="🟢 Низкая", callback_data=f"set_priority:{task_text}:3")
        ]
    ])

    await message.answer(
        "Выберите приоритет задачи:",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("set_priority:"))
async def set_task_priority(callback: types.CallbackQuery):
    _, task_text, priority = callback.data.split(":")
    user_id = callback.from_user.id
    today_date = get_today_date()

    try:
        cursor.execute(
            'INSERT INTO daily_tasks (user_id, task, date, priority) VALUES (?, ?, ?, ?)',
            (user_id, task_text, today_date, int(priority)))
        conn.commit()
        await callback.message.edit_text(f"Задача '{task_text}' добавлена с приоритетом {priority}!")
    except sqlite3.IntegrityError:
        await callback.message.edit_text("Такая задача уже существует.")
    except Exception as e:
        logging.error(f"Ошибка добавления задачи: {e}")
        await callback.message.edit_text("Произошла ошибка при добавлении задачи.")


#  КАЛЕНДАРЬ
async def show_calendar(message: types.Message, year: int = None, month: int = None):
    # Показывает интерактивный календарь
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    kb_builder = InlineKeyboardBuilder()

    # Заголовок с месяцем и годом
    month_name = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"][month - 1]
    kb_builder.row(InlineKeyboardButton(
        text=f"{month_name} {year}",
        callback_data="ignore"
    ))

    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    kb_builder.row(*[InlineKeyboardButton(text=day, callback_data="ignore") for day in week_days])

    # Получаю первый день месяца и количество дней
    first_day = datetime(year, month, 1)
    days_in_month = (datetime(year, month + 1, 1) - timedelta(days=1)).day if month < 12 else 31

    # Заполняю календарь
    weeks = []
    current_week = []

    # Пустые клетки до первого дня
    for _ in range(first_day.weekday()):
        current_week.append(InlineKeyboardButton(text=" ", callback_data="ignore"))

    # Дни месяца
    for day in range(1, days_in_month + 1):
        date = datetime(year, month, day)
        if date.date() < now.date():  # Прошедшие дни неактивны
            current_week.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
        else:
            current_week.append(InlineKeyboardButton(
                text=str(day),
                callback_data=f"trip_date:{year}-{month:02d}-{day:02d}"
            ))

        if len(current_week) == 7:
            weeks.append(current_week)
            current_week = []

    # Добавляю последнюю неделю
    if current_week:
        weeks.append(current_week)

    # Добавляю недели в клавиатуру
    for week in weeks:
        kb_builder.row(*week)

    # Кнопки навигации
    prev_year, next_year = year, year
    prev_month = month - 1
    next_month = month + 1

    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
    if next_month > 12:
        next_month = 1
        next_year += 1

    kb_builder.row(
        InlineKeyboardButton(
            text="←",
            callback_data=f"calendar:{prev_year}-{prev_month}"
        ),
        InlineKeyboardButton(
            text="→",
            callback_data=f"calendar:{next_year}-{next_month}"
        )
    )

    await message.answer(
        "Выберите дату поездки:",
        reply_markup=kb_builder.as_markup()
    )


@dp.callback_query(F.data.startswith("calendar:"))
async def process_calendar_navigation(callback: types.CallbackQuery):
    # Обработка переключения месяцев в календаре
    _, year_month = callback.data.split(":")
    year, month = map(int, year_month.split("-"))
    await callback.message.delete()
    await show_calendar(callback.message, year, month)


@dp.callback_query(F.data.startswith("trip_date:"))
async def process_date_selection(callback: types.CallbackQuery):
    # Обработка выбора даты из календаря
    _, date_str = callback.data.split(":")
    user_id = callback.from_user.id

    # Сохраняю дату и переходим к следующему шагу
    trip_states[user_id] = {
        'step': 'awaiting_time',
        'data': {
            'date': date_str
        }
    }

    await callback.message.delete()
    await callback.message.answer(
        f"📅 Выбрана дата: {date_str}\n"
        f"⏰ Теперь введите время поездки в формате ЧЧ:ММ (например, 14:30):",
        reply_markup=back_keyboard
    )


@dp.message(F.text == "Добавить поездку")
async def add_trip(message: types.Message):
    # Начало добавления поездки - показываем календарь
    await show_calendar(message)


#   ОБРАБОТЧИКИ
@dp.message(F.text == "создать стикер")
async def handle_create_sticker(message: types.Message):
    stic_user_data[message.from_user.id] = {}
    await stic_start(message)


@dp.message(F.photo)
async def handle_photo(message: types.Message):
    if message.from_user.id in stic_user_data:
        stic_user_data[message.from_user.id] = {
            'image_file_id': message.photo[-1].file_id,
            'chat_id': message.chat.id
        }
        await stic_photo_handler(message)


@dp.message(lambda message: message.from_user.id in stic_user_data)
async def handle_text_for_sticker(message: types.Message):
    await stic_caption_handler(message)


def get_user_tasks(user_id):
    cursor.execute('SELECT id, task FROM daily_tasks WHERE user_id = ? AND date = ?', (user_id, get_today_date()))
    return cursor.fetchall()


def get_today_date():
    return datetime.now().strftime('%Y-%m-%d')


def get_task_status(user_id, task_id, date):
    cursor.execute('SELECT done FROM daily_tasks_status WHERE user_id = ? AND task_id = ? AND date = ?',
                   (user_id, task_id, date))
    row = cursor.fetchone()
    return row[0] if row else 0


async def show_progress(message: types.Message):
    # Показываю прогресс пользователя
    user_id = message.from_user.id
    cursor.execute('''
        SELECT tasks_completed, high_priority_completed, streaks 
        FROM user_stats 
        WHERE user_id = ?
    ''', (user_id,))

    stats = cursor.fetchone()

    if not stats:
        await message.reply("Вы еще не выполнили ни одной задачи. Начните планировать!", reply_markup=main_keyboard)
        return

    tasks_completed, high_priority_completed, streaks = stats

    text = (
        "📊 Ваш прогресс:\n\n"
        f"✅ Всего выполнено задач: {tasks_completed}\n"
        f"🔴 Задач с высоким приоритетом: {high_priority_completed}\n"
        f"🔥 Текущая серия: {streaks} дней подряд\n\n"
        "Продолжайте в том же духе!"
    )

    await message.reply(text, reply_markup=main_keyboard)


def set_task_status(user_id, task_id, date, done):
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO daily_tasks_status 
            (user_id, task_id, date, done) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, task_id, date, done))

        # Если задача выполнена, обновляем статистику
        if done:
            priority = get_task_priority(task_id)
            update_user_stats(user_id, priority)
            new_badges = check_achievements(user_id)
            return True, new_badges
        return True, []
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса задачи: {e}")
        return False, []


async def send_tasks_with_status(message: types.Message):
    user_id = message.from_user.id
    today_date = get_today_date()

    cursor.execute('''
        SELECT t.id, t.task, t.priority, s.done 
        FROM daily_tasks t
        LEFT JOIN daily_tasks_status s ON t.id = s.task_id AND s.user_id = t.user_id AND s.date = ?
        WHERE t.user_id = ? AND t.date = ?
    ''', (today_date, user_id, today_date))

    tasks = cursor.fetchall()

    if not tasks:
        await message.reply(
            "У вас пока нет ежедневных дел на сегодня. Пожалуйста, добавьте задачу, отправив текст задачи.",
            reply_markup=main_keyboard
        )
        return

    text = "Ваши ежедневные дела на сегодня:\n"
    for i, (task_id, task_text, priority, done) in enumerate(tasks, 1):
        status = "✅" if done else "❌"
        priority_icon = "🔴" if priority == 1 else "🟡" if priority == 2 else "🟢"
        text += f"{i}. {priority_icon} {task_text} {status}\n"
    text += "\nЧтобы отметить задачу выполненной, отправьте её номер."

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
            (user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
        )
        conn.commit()
        await message.reply("Вы успешно зарегистрированы!", reply_markup=main_keyboard)
    else:
        await message.reply("Вы уже зарегистрированы.", reply_markup=main_keyboard)


@dp.message(Command('help'))
async def help_command(message: types.Message):
    await message.reply("Выберите опцию:", reply_markup=main_keyboard)


async def show_upcoming_trips(message: types.Message):
    user_id = message.from_user.id
    today = datetime.now().strftime('%Y-%m-%d')

    cursor.execute('''
        SELECT destination, date, time, address 
        FROM trips 
        WHERE user_id = ? AND date >= ?
        ORDER BY date, time
    ''', (user_id, today))

    trips = cursor.fetchall()

    if not trips:
        await message.reply("У вас нет запланированных поездок.", reply_markup=trips_keyboard)
        return

    response = "Ваши запланированные поездки:\n\n"
    for i, (destination, date, time, address) in enumerate(trips, 1):
        map_url = f"https://yandex.ru/maps/?text={address.replace(' ', '+')}"
        response += (
            f"{i}. 🚗 {destination}\n"
            f"   📅 {date} ⏰ {time}\n"
            f"   📍 {address}\n"
            f"   🗺 [Открыть на карте]({map_url})\n\n"
        )

    await message.reply(response, reply_markup=trips_keyboard, disable_web_page_preview=True)


@dp.message(F.text == "Добавить поездку")
async def add_trip(message: types.Message):
    # Начало добавления поездки - показываю календарь
    await show_calendar(message.chat.id)


@dp.message(F.text == "Добавить задачу")
async def add_task_handler(message: types.Message):
    user_states[message.from_user.id] = 'awaiting_task'
    await message.reply("Пожалуйста, введите текст задачи:", reply_markup=main_keyboard)


def get_task_priority(task_id: int) -> int:
    # Возвращаю приоритет задачи
    cursor.execute('SELECT priority FROM daily_tasks WHERE id = ?', (task_id,))
    result = cursor.fetchone()
    return result[0] if result else 3


@dp.message()
async def handle_buttons(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    logging.info(f"Received message: {text} from user: {user_id}")

    if text == "Планирование":
        user_states[user_id] = None
        await message.reply("Вы выбрали 'Планирование'.", reply_markup=planning_keyboard)
        return

    elif text == "Поездки":
        await message.reply("Вы выбрали 'Поездки'. Что вы хотите сделать?", reply_markup=trips_keyboard)
        return

    elif text == "Посмотреть мои поездки":
        await show_upcoming_trips(message)
        return

    elif text == "Посмотреть список дел":
        await send_tasks_with_status(message)
        return

    elif text == "Назад":
        await message.reply("Возвращаемся в главное меню", reply_markup=main_keyboard)
        return

    # Обработка состояний
    state = user_states.get(user_id)

    if user_states.get(user_id) == 'awaiting_task':
        await ask_task_priority(message, text)
        user_states.pop(user_id)
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
                success, new_badges = set_task_status(user_id, task_id, today_date, new_status)
                if success:
                    status_text = "выполнена ✅" if new_status == 1 else "не выполнена ❌"
                    reply_text = f"Задача '{task_text}' отмечена как {status_text}."
                    if new_status == 1 and new_badges:
                        reply_text += "\n\n🎉 Новые достижения:\n"
                        for name, desc in new_badges:
                            reply_text += f"🏅 {name}: {desc}\n"
                    await message.reply(reply_text, reply_markup=main_keyboard)
                else:
                    await message.reply("Не удалось обновить статус задачи.", reply_markup=main_keyboard)
                user_states.pop(user_id)
            else:
                await message.reply("Неверный номер задачи.", reply_markup=main_keyboard)
        except ValueError:
            await message.reply("Пожалуйста, введите номер задачи.", reply_markup=main_keyboard)
        return

    # Обработка состояния поездки
    if user_id in trip_states:
        state = trip_states[user_id]
        step = state['step']
        data = state['data']

        if step == 'awaiting_time':
            try:
                datetime.strptime(text, '%H:%M')
                data['time'] = text
                state['step'] = 'awaiting_address'
                await message.reply("Введите адрес или место назначения:", reply_markup=back_keyboard)
            except ValueError:
                await message.reply("Неверный формат времени. Попробуйте снова (ЧЧ:ММ).", reply_markup=back_keyboard)
            return

        elif step == 'awaiting_address':
            data['address'] = text
            data['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            try:
                cursor.execute('''
                    INSERT INTO trips (user_id, destination, date, time, address, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, text, data['date'], data['time'], data['address'], data['created_at']))
                conn.commit()

                map_url = f"https://yandex.ru/maps/?text={text.replace(' ', '+')}"
                await message.reply(
                    f"🚗 Поездка добавлена!\n"
                    f"📅 Дата: {data['date']}\n"
                    f"⏰ Время: {data['time']}\n"
                    f"📍 Адрес: {data['address']}\n\n"
                    f"🗺 Открыть на карте: {map_url}",
                    reply_markup=main_keyboard
                )
            except Exception as e:
                logging.error(f"Ошибка при сохранении поездки: {e}")
                await message.reply("Произошла ошибка при сохранении поездки.", reply_markup=main_keyboard)
            finally:
                trip_states.pop(user_id)
            return

    await message.reply("Я не понимаю эту команду.", reply_markup=main_keyboard)


async def reminder_loop(bot: Bot):
    user_last_meme = {}
    meme_messages = [
        {"text": "⏰ Осталось совсем мало времени! Поторопись!", "photo": "https://ltdfoto.ru/image/s4WGxu"},
        {"text": "🔥 Время тикает! Не откладывай на потом!", "photo": "https://ltdfoto.ru/image/s4WQ6Z"},
        {"text": "🚀 Ты можешь это сделать! Осталось совсем немного!",
         "photo": "https://ltdfoto.ru/images/2025/04/20/CAK-NORIS.jpg"},
        {"text": "Будь как Челентано!", "photo": "https://ltdfoto.ru/images/2025/04/20/CELENTANO.jpg"},
        {"text": "Помни об этом!", "photo": "https://ltdfoto.ru/images/2025/04/20/DI-KAPRIO-1.jpg"}
    ]

    # Интервалы напоминаний для каждого приоритета
    priority_intervals = {
        1: 60 * 60,
        2: 2 * 60 * 60,
        3: 3 * 60 * 60
    }

    # Время последнего напоминания для каждой задачи каждого пользователя
    last_reminder_time = {}

    while True:
        now = datetime.now()
        today = get_today_date()

        # Получаю все незавершенные задачи всех пользователей
        cursor.execute('''
            SELECT t.user_id, t.id, t.task, t.priority, s.done 
            FROM daily_tasks t
            LEFT JOIN daily_tasks_status s ON t.id = s.task_id AND s.user_id = t.user_id AND s.date = ?
            WHERE t.date = ? AND (s.done = 0 OR s.done IS NULL)
        ''', (today, today))

        tasks = cursor.fetchall()

        for user_id, task_id, task_text, priority, _ in tasks:
            # Проверяю, нужно ли отправлять напоминание для этой задачи
            last_time = last_reminder_time.get((user_id, task_id), datetime.min)
            time_since_last = (now - last_time).total_seconds()

            if time_since_last >= priority_intervals[priority]:
                try:
                    if user_id not in user_last_meme:
                        user_last_meme[user_id] = {'last_type': 'text', 'meme_index': 0}

                    # Определяю тип сообщения (текст или мем)
                    if user_last_meme[user_id]['last_type'] == 'text':
                        meme_index = user_last_meme[user_id]['meme_index']
                        meme = meme_messages[meme_index]

                        try:
                            await bot.send_photo(
                                user_id,
                                photo=meme["photo"],
                                caption=f"{meme['text']}\n\nЗадача: {task_text}\nПриоритет: {'🔴 Высокий' if priority == 1 else '🟡 Средний' if priority == 2 else '🟢 Низкий'}",
                                reply_markup=main_keyboard
                            )
                        except Exception as e:
                            logging.error(f"Ошибка отправки мема: {e}")
                            await bot.send_message(
                                user_id,
                                f"{meme['text']}\n\nЗадача: {task_text}\nПриоритет: {'🔴 Высокий' if priority == 1 else '🟡 Средний' if priority == 2 else '🟢 Низкий'}",
                                reply_markup=main_keyboard
                            )

                        user_last_meme[user_id]['meme_index'] = (meme_index + 1) % len(meme_messages)
                        user_last_meme[user_id]['last_type'] = 'photo'
                    else:
                        await bot.send_message(
                            user_id,
                            f"🔔 Напоминание о задаче:\n{task_text}\nПриоритет: {'🔴 Высокий' if priority == 1 else '🟡 Средний' if priority == 2 else '🟢 Низкий'}",
                            reply_markup=main_keyboard
                        )
                        user_last_meme[user_id]['last_type'] = 'text'

                    # Обновляю время последнего напоминания
                    last_reminder_time[(user_id, task_id)] = now

                except Exception as e:
                    logging.error(f"Ошибка напоминания для {user_id}: {e}")
                    user_last_meme[user_id] = {'last_type': 'text', 'meme_index': 0}

        await asyncio.sleep(10)  # Проверяю каждую минуту


async def trip_reminder_loop(bot: Bot):
    while True:
        await asyncio.sleep(60)

        now = datetime.now()
        current_time = now.strftime('%H:%M')
        current_date = now.strftime('%Y-%m-%d')

        cursor.execute('''
            SELECT user_id, destination, date, time, address 
            FROM trips 
            WHERE date = ?
        ''', (current_date,))

        upcoming_trips = cursor.fetchall()

        for trip in upcoming_trips:
            user_id, destination, date, time, address = trip
            trip_start_time = datetime.strptime(f"{date} {time}", '%Y-%m-%d %H:%M')
            time_diff = (trip_start_time - now).total_seconds() / 60

            if 29.5 < time_diff <= 30:
                await bot.send_message(
                    user_id,
                    f"🚗 Напоминание: до поездки в {destination} осталось 30 минут!\n"
                    f"📅 Дата: {date}\n⏰ Время: {time}\n📍 Адрес: {address}",
                    reply_markup=main_keyboard
                )
            elif 59.5 < time_diff <= 60:
                await bot.send_message(
                    user_id,
                    f"🚗 Напоминание: до поездки в {destination} остался 1 час!\n"
                    f"📅 Дата: {date}\n⏰ Время: {time}\n📍 Адрес: {address}",
                    reply_markup=main_keyboard
                )


if __name__ == '__main__':
    bot = Bot(token=BOT_TOKEN)


    async def main():
        asyncio.create_task(reminder_loop(bot))
        asyncio.create_task(trip_reminder_loop(bot))
        try:
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"Ошибка в работе бота: {e}")
        finally:
            await bot.session.close()


    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен пользователем")
    except Exception as e:
        logging.error(f"Фатальная ошибка: {e}")
    finally:
        conn.close()
