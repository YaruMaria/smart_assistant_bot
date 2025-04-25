import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram import F
from sqlalchemy import create_engine, Column, Integer, String, LargeBinary, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from PIL import Image, ImageDraw, ImageFont
from aiogram.types import BufferedInputFile


os.makedirs("downloads", exist_ok=True)
# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Настройка базы данных
DATABASE_URL = "sqlite:///sticker.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine, expire_on_commit=False)


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    stickers = relationship("Sticker", back_populates="user")


class Sticker(Base):
    __tablename__ = 'stickers'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    image_data = Column(LargeBinary, nullable=False)
    caption = Column(String(500))
    user = relationship("User", back_populates="stickers")


def init_db():
    Base.metadata.create_all(engine)
    logger.info("Database initialized")


# Инициализация базы данных
init_db()

# Настройка бота
API_TOKEN = '7585920451:AAFr1eFDKgH37GoqztPry9uw0XHWUTcVCrM'
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Глобальные переменные для хранения данных
user_data = {}


async def add_user_if_not_exists(session, telegram_id):
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        session.add(user)
        session.commit()
        logger.info(f"New user added: {telegram_id}")
    return user


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    session = Session()
    try:
        await add_user_if_not_exists(session, message.from_user.id)
        await message.reply("Привет! Отправь мне изображение, чтобы создать стикер.")
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}")
        await message.reply("Произошла ошибка. Пожалуйста, попробуйте позже.")
    finally:
        session.close()


@dp.message(F.photo)
async def photo_handler(message: types.Message):
    user_data[message.from_user.id] = {
        'image_file_id': message.photo[-1].file_id,
        'chat_id': message.chat.id
    }
    await message.reply("Отлично! Теперь напиши текст для стикера.")


async def process_image(file_id, chat_id):
    try:
        photo = await bot.get_file(file_id)
        os.makedirs("downloads", exist_ok=True)
        photo_path = f"downloads/{photo.file_id}.jpg"
        await bot.download_file(photo.file_path, photo_path)
        return photo_path
    except Exception as e:
        logger.error(f"Error downloading image: {e}")
        await bot.send_message(chat_id, "Произошла ошибка при загрузке изображения.")
        return None


async def save_sticker_to_db(session, user_id, sticker_data, caption):
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            user = await add_user_if_not_exists(session, user_id)

        new_sticker = Sticker(
            image_data=sticker_data,
            caption=caption,
            user_id=user.id
        )
        session.add(new_sticker)
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving sticker to DB: {e}")
        session.rollback()
        return False




from aiogram.types import BufferedInputFile

@dp.message(F.from_user.id.in_(user_data.keys()))
async def caption_handler(message: types.Message):
    user_id = message.from_user.id
    user_info = user_data.get(user_id, {})

    if 'image_file_id' not in user_info:
        await message.reply("Пожалуйста, сначала отправьте изображение.")
        return

    photo_path = None
    sticker_path = None

    try:
        # Обработка изображения
        photo_path = await process_image(user_info['image_file_id'], user_info['chat_id'])
        if not photo_path:
            return

        # Создание стикера
        sticker_path = create_sticker(photo_path, message.text)
        if not sticker_path:
            await message.reply("Не удалось создать стикер.")
            return

        # Сохранение в БД
        session = Session()
        with open(sticker_path, 'rb') as f:
            sticker_data = f.read()
            if not await save_sticker_to_db(session, user_id, sticker_data, message.text):
                await message.reply("Ошибка при сохранении стикера.")
                return

        # Отправка стикера
        with open(sticker_path, 'rb') as f:
            sticker_bytes = f.read()
            input_file = BufferedInputFile(sticker_bytes, filename="sticker.png")
            await bot.send_sticker(chat_id=user_info['chat_id'], sticker=input_file)
            await message.reply("✅ Ваш стикер готов!")

    except Exception as e:
        logger.error(f"Error in caption_handler: {e}")
        await message.reply("Произошла ошибка. Пожалуйста, попробуйте еще раз.")
    finally:
        # Очистка
        if photo_path and os.path.exists(photo_path):
            os.remove(photo_path)
        if sticker_path and os.path.exists(sticker_path):
            os.remove(sticker_path)
        user_data.pop(user_id, None)


def create_sticker(image_path, text):
    try:
        # Открываю изображение
        image = Image.open(image_path)
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # Создаю слой для текста
        txt_layer = Image.new('RGBA', image.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_layer)

        # Настройки шрифта
        try:
            font = ImageFont.truetype("arial.ttf", 100)
        except:
            font = ImageFont.load_default()
            font.size = 60  # Увеличиваю размер стандартного шрифта

        #  размеры текста
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        # текст вверху
        x = (image.width - text_width) / 2
        y = 20  # Отступ сверху вместо image.height - text_height - 20

        # Рисую текст с обводкой
        draw.text(
            (x, y),
            text,
            fill="white",
            font=font,
            stroke_width=3,  #  обводка
            stroke_fill="black",
            align="center"
        )

        # Объединяю слои
        result = Image.alpha_composite(image, txt_layer)
        sticker_path = f"downloads/sticker_{os.path.basename(image_path)}.png"
        result.save(sticker_path, "PNG", quality=95)

        return sticker_path
    except Exception as e:
        logger.error(f"Error creating sticker: {e}")
        return None


async def main():
    logger.info("Starting bot...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot stopped with error: {e}")
    finally:
        await bot.session.close()
        logger.info("Bot stopped")


user_data = user_data  # Делаю переменную доступной для импорта
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")