import sqlite3
from aiogram import types
from aiogram.dispatcher import Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import State, StatesGroup
import asyncio
from datetime import datetime, timedelta


# Создаем состояния для управления состоянием пользователя
class TripStates(StatesGroup):
    main_menu = State()
    waiting_for_action = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_address = State()


# Создаем соединение с базой данных
conn = sqlite3.connect('trips.db')
cursor = conn.cursor()

# Создаем таблицу для хранения поездок
cursor.execute('''
 CREATE TABLE IF NOT EXISTS trips (
     user_id INTEGER,
     date TEXT,
     time TEXT,
     address TEXT,
     additional_info TEXT
 )
 ''')
conn.commit()


async def start_trip(message: types.Message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Запланировать поездку", "Посмотреть сегодняшние поездки")
    await message.reply("Выберите действие:", reply_markup=markup)
    await TripStates.main_menu.set()


async def handle_action(message: types.Message, state: FSMContext):
    if message.text == "Запланировать поездку":
        await message.reply("Введите дату поездки (в формате ГГГГ-ММ-ДД):")
        await TripStates.waiting_for_date.set()
    elif message.text == "Посмотреть сегодняшние поездки":
        await show_today_trips(message.from_user.id)
    await state.finish()  # Завершаем состояние


async def show_today_trips(user_id):
    today = datetime.now().date()
    cursor.execute("SELECT * FROM trips WHERE user_id = ? AND date = ?", (user_id, today))
    trips = cursor.fetchall()

    if trips:
        response = "Сегодняшние поездки:\n"
        for trip in trips:
            response += f"Дата: {trip[1]}, Время: {trip[2]}, Адрес: {trip[3]}\n"
        await message.reply(response)
    else:
        await message.reply("У вас нет запланированных поездок на сегодня.")


async def process_date(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    date = message.text

    await state.update_data(date=date)  # Сохраняем дату в состоянии
    await message.reply("Введите время поездки (в формате ЧЧ:ММ):")
    await TripStates.waiting_for_time.set()  # Переход к следующему состоянию


async def process_time(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    time = message.text

    await state.update_data(time=time)  # Сохраняем время в состоянии
    await message.reply("Введите адрес поездки:")
    await TripStates.waiting_for_address.set()  # Переход к следующему состоянию


async def process_address(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    address = message.text

    # Получаем данные из состояния
    data = await state.get_data()
    date = data.get('date')
    time = data.get('time')

    # Сохраняем поездку в базе данных
    cursor.execute(
        'INSERT INTO trips (user_id, date, time, address) VALUES (?, ?, ?, ?)',
        (user_id, date, time, address)
    )
    conn.commit()

    await message.reply(f"Поездка запланирована на {date} в {time} по адресу: {address}.")

    # Запускаем напоминание
    asyncio.create_task(send_reminder(user_id, date, time, address))

    await state.finish()  # Завершаем состояние


# Функция для отправки напоминания
async def send_reminder(user_id, date, time, address):
    reminder_time = f"{date} {time}"
    reminder_datetime = datetime.strptime(reminder_time, "%Y-%m-%d %H:%M")
    now = datetime.now()
    wait_time = (reminder_datetime - now - timedelta(hours=1)).total_seconds()

    if wait_time > 0:
        await asyncio.sleep(wait_time)  # Ожидаем до времени напоминания
        await bot.send_message(user_id, f"Напоминание: Ваша поездка по адресу {address} начинается через 1 час.")
    else:
        # Если время уже прошло, отправляем уведомление сразу
        await bot.send_message(user_id, f"Напоминание: Ваша поездка по адресу {address} начинается сейчас!")

# Функция для получения дополнительной информации о месте
async def get_additional_info(address):
    # Здесь вы можете интегрировать API (например, Google Places API)
    # для получения информации о предприятии, таком как аптека
    # Для примера, просто вернем фиктивные данные
    if "аптека" in address.lower():
        return "Дополнительная информация:\nГрафик работы: 9:00 - 21:00\nТелефон: 123-456-7890\nСайт: www.apteka-example.com"
    return "Дополнительная информация не найдена."

# Основная функция для обработки сообщений
async def on_message(message: types.Message, state: FSMContext):
    if message.text.lower() == "/start":
        await start_trip(message)
    else:
        current_state = await state.get_state()
        if current_state == TripStates.main_menu.state:
            await handle_action(message, state)
        elif current_state == TripStates.waiting_for_date:
            await process_date(message, state)
        elif current_state == TripStates.waiting_for_time:
            await process_time(message, state)
        elif current_state == TripStates.waiting_for_address:
            await process_address(message, state)
        else:
            await message.reply("Пожалуйста, используйте команду /start для начала.")

# Настройка бота и диспетчера
bot = Bot(token='YOUR_BOT_TOKEN')
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Регистрация обработчиков
dp.register_message_handler(on_message)

# Запуск бота
if __name__ == '__main__':
    import asyncio
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)

