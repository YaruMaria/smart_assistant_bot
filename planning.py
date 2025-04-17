# planning.py
from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import sqlite3

# Подключение к базе данных
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Хранилище состояния для планирования
planning_states = {}

reply_keyboard_planning = [
    [KeyboardButton(text="Добавить план")],
    [KeyboardButton(text="Проверить планы")]
]
kb_planning = ReplyKeyboardMarkup(keyboard=reply_keyboard_planning, resize_keyboard=True, one_time_keyboard=False)

async def handle_planning(message: types.Message):
    user_id = message.from_user.id
    text = message.text

    if text == "Добавить план":
        planning_states[user_id] = 'awaiting_plan'
        await message.reply("Пожалуйста, введите текст плана, который хотите добавить.", reply_markup=kb_planning)
    elif text == "Проверить планы":
        await send_plans_with_status(message)
    else:
        await message.reply("Пожалуйста, используйте клавиатуру для выбора опций.", reply_markup=kb_planning)

async def send_plans_with_status(message: types.Message):
    user_id = message.from_user.id
    plans = get_user_plans(user_id)

    if not plans:
        await message.reply("У вас пока нет планов. Добавьте новый план.", reply_markup=kb_planning)
        return

    text = "Ваши планы:\n"
    for i, (plan_id, plan_text) in enumerate(plans, 1):
        text += f"{i}. {plan_text}\n"
    await message.reply(text, reply_markup=kb_planning)

def get_user_plans(user_id):
    cursor.execute('SELECT id, plan FROM user_plans WHERE user_id = ?', (user_id,))
    return cursor.fetchall()

def add_user_plan(user_id, plan_text):
    try:
        cursor.execute('INSERT INTO user_plans (user_id, plan) VALUES (?, ?)', (user_id, plan_text))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # План уже существует

async def process_plan_input(message: types.Message):
    user_id = message.from_user.id
    if user_id in planning_states and planning_states[user_id] == 'awaiting_plan':
        plan_text = message.text
        add_user_plan(user_id, plan_text)
        await message.reply("План успешно добавлен!", reply_markup=kb_planning)
        del planning_states[user_id]  # Удаляем состояние после добавления плана
    else:
        await handle_planning(message)

