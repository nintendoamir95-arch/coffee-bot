import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

# НАСТРОЙКИ: Замените на ваш токен от @BotFather и ваш Telegram ID главного владельца
TOKEN = "9284816680:AAF8bW3XUqspC1G65VkBPfqK2Ux6NNf7Ns8"
OWNER_ID = 5113890948  # Узнать свой ID можно у ботов вроде @userinfobot

# Инициализация базы данных (все таблицы в одном месте)
def init_db():
    conn = sqlite3.connect("coffee_bot.db")
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            language TEXT DEFAULT 'ru',
            role TEXT DEFAULT 'client' -- client, staff, admin, owner
        )
    """)

    # Таблица продуктов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_ru TEXT,
            name_uz TEXT,
            name_en TEXT,
            country TEXT,
            method TEXT, -- filter или espresso
            price_250g REAL,
            price_500g REAL,
            price_1kg REAL,
            image_id TEXT
        )
    """)

    # Таблица заказов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            details TEXT,
            total_price REAL,
            status TEXT DEFAULT 'pending'
        )
    """)

    # Таблица подписок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            weight_type TEXT, -- 025, 050, 100
            period TEXT,      -- week, month
            status TEXT DEFAULT 'active'
        )
    """)
    conn.commit()
    conn.close()

init_db()

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()

# Локализация интерфейса (RU, UZ, EN)
LANGS = {
    "ru": {
        "welcome": "☕ Добро пожаловать в элитный кофейный клуб!",
        "menu": "Главное меню:",
        "catalog": "🛒 Каталог кофе",
        "subscriptions": "📦 Подписки",
        "admin_panel": "⚙️ Админ-панель",
    },
    "uz": {
        "welcome": "☕ Premium qahva klubiga xush kelibsiz!",
        "menu": "Asosiy menyu:",
        "catalog": "🛒 Qahva katalogi",
        "subscriptions": "📦 Obunalar",
        "admin_panel": "⚙️ Admin paneli",
    },
    "en": {
        "welcome": "☕ Welcome to the specialty coffee club!",
        "menu": "Main menu:",
        "catalog": "🛒 Coffee Catalog",
        "subscriptions": "📦 Subscriptions",
        "admin_panel": "⚙️ Admin Panel",
    },
}

# FSM Состояния для добавления продукта через телефон
class AddProductStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_name_ru = State()
    waiting_for_name_uz = State()
    waiting_for_name_en = State()
    waiting_for_country = State()
    waiting_for_method = State()
    waiting_for_price_250g = State()
    waiting_for_price_500g = State()
    waiting_for_price_1kg = State()

# Команда /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    role = "owner" if user_id == OWNER_ID else "client"

    conn = sqlite3.connect("coffee_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (telegram_id, role) VALUES (?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET role = excluded.role
    """, (user_id, role))
    conn.commit()
    conn.close()

    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="lang_ru")
    kb.button(text="🇺🇿 O'zbekcha", callback_data="lang_uz")
    kb.button(text="🇬🇧 English", callback_data="lang_en")
    kb.adjust(3)

    await message.answer("☕ Выберите язык / Tilni tanlang / Choose language:", reply_markup=kb.as_markup())

# Смена языка
@router.callback_query(F.data.startswith("lang_"))
async def set_language(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    conn = sqlite3.connect("coffee_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET language = ? WHERE telegram_id = ?", (lang, callback.from_user.id))
    conn.commit()
    conn.close()

    await show_main_menu_msg(callback.message, lang)
    await callback.answer()

async def show_main_menu_msg(message: Message, lang: str):
    text_dict = LANGS.get(lang, LANGS["ru"])
    kb = InlineKeyboardBuilder()
    kb.button(text=text_dict["catalog"], callback_data="show_catalog")
    kb.button(text=text_dict["subscriptions"], callback_data="show_subs")

    # Проверка прав админа/персонала
    conn = sqlite3.connect("coffee_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (message.chat.id,))
    res = cursor.fetchone()
    conn.close()

    if res and res[0] in ["admin", "owner", "staff"]:
        kb.button(text=text_dict["admin_panel"], callback_data="admin_root")

    kb.adjust(1)
    await message.answer(text_dict["menu"], reply_markup=kb.as_markup())

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    conn = sqlite3.connect("coffee_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT language FROM users WHERE telegram_id = ?", (callback.from_user.id,))
    res = cursor.fetchone()
    conn.close()
    lang = res[0] if res else "ru"
    await show_main_menu_msg(callback.message, lang)
    await callback.answer()

# Просмотр каталога
@router.callback_query(F.data == "show_catalog")
async def show_catalog(callback: CallbackQuery):
    conn = sqlite3.connect("coffee_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name_ru, country, price_250g, price_500g, price_1kg, image_id FROM products LIMIT 1")
    product = cursor.fetchone()
    conn.close()

    if not product:
        await callback.message.answer("⚠️ Каталог пока пуст. Администратор добавляет новинки через телефон.")
        await callback.answer()
        return

    prod_id, name, country, p250, p500, p1kg, img_id = product
    
    caption = (
        f"🌍 **{country.upper()} SPECIALTY COFFEE**\n\n"
        f"🏷 **{name}**\n\n"
        f"⚖️ **Цены по весу:**\n"
        f"• 0.25 кг — {p250:,.0f} сум\n"
        f"• 0.50 кг — {p500:,.0f} сум\n"
        f"• 1.00 кг — {p1kg:,.0f} сум\n\n"
        f"🚚 *Доставка:* Бесплатно от 250,000 сум (фильтр) / от 500,000 сум (эспрессо)."
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="0.25 кг", callback_data=f"buy_{prod_id}_025")
    kb.button(text="0.5 кг", callback_data=f"buy_{prod_id}_050")
    kb.button(text="1 кг", callback_data=f"buy_{prod_id}_100")
    kb.adjust(3)

    if img_id:
        await callback.message.answer_photo(photo=img_id, caption=caption, reply_markup=kb.as_markup(), parse_mode="Markdown")
    else:
        await callback.message.answer(text=caption, reply_markup=kb.as_markup(), parse_mode="Markdown")
    
    await callback.answer()

# Расчет бесплатной доставки
def calculate_delivery_cost(method: str, total_price: float):
    threshold = 250000 if method == "filter" else 500000
    fee = 0 if total_price >= threshold else 30000
    return fee, threshold

# Выбор веса и оформление подписки/покупки
@router.callback_query(F.data.startswith("buy_"))
async def process_weight(callback: CallbackQuery):
    _, prod_id, weight_code = callback.data.split("_")
    
    conn = sqlite3.connect("coffee_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name_ru, method, price_250g, price_500g, price_1kg FROM products WHERE id = ?", (prod_id,))
    prod = cursor.fetchone()
    conn.close()
    
    name, method, p250, p500, p1kg = prod
    price = p250 if weight_code == "025" else (p500 if weight_code == "050" else p1kg)
    
    delivery_fee, threshold = calculate_delivery_cost(method, price)
    final_total = price + delivery_fee
    
    text = (
        f"🛒 **Выбран лот:** {name}\n"
        f"💵 Стоимость кофе: {price:,.0f} сум\n"
        f"🚚 Доставка: {'Бесплатно 🎉' if delivery_fee == 0 else f'{delivery_fee:,.0f} сум (до порога не хватает {threshold - price:,.0f} сум)'}\n\n"
        f"💳 **Итого:** {final_total:,.0f} сум\n\nВыберите формат:"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Разовая покупка", callback_data=f"order_once_{prod_id}_{weight_code}")
    kb.button(text="📦 Подписка на неделю (-10%)", callback_data=f"sub_week_{prod_id}_{weight_code}")
    kb.button(text="📦 Подписка на месяц (-15%)", callback_data=f"sub_month_{prod_id}_{weight_code}")
    kb.adjust(1)
    
    await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("sub_"))
async def process_sub(callback: CallbackQuery):
    parts = callback.data.split("_")
    period, prod_id, weight_code = parts[1], parts[2], parts[3]
    
    conn = sqlite3.connect("coffee_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO subscriptions (user_id, product_id, weight_type, period, status) VALUES (?, ?, ?, ?, 'active')",
                   (callback.from_user.id, prod_id, weight_code, period))
    conn.commit()
    conn.close()
    
    await callback.message.answer("🎉 **Подписка успешно оформлена!** Менеджер свяжется с вами для подключения оплаты (Click / Payme / Карты).", parse_mode="Markdown")
    await callback.answer()

# --- АДМИН ПАНЕЛЬ И FSM ЗАГРУЗКА ---
@router.callback_query(F.data == "admin_root")
async def admin_root(callback: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить лот кофе", callback_data="admin_add_product")
    kb.button(text="🔙 В главное меню", callback_data="back_to_main")
    kb.adjust(1)
    await callback.message.edit_text("⚙️ **Панель управления:**", reply_markup=kb.as_markup(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "admin_add_product")
async def start_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddProductStates.waiting_for_photo)
    await callback.message.answer("📸 Отправьте **фотографию кофе** с телефона:")
    await callback.answer()

@router.message(AddProductStates.waiting_for_photo, F.photo)
async def fsm_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(AddProductStates.waiting_for_name_ru)
    await message.answer("🇷🇺 Введите название кофе на **русском**:")

@router.message(AddProductStates.waiting_for_name_ru)
async def fsm_ru(message: Message, state: FSMContext):
    await state.update_data(name_ru=message.text)
    await state.set_state(AddProductStates.waiting_for_name_uz)
    await message.answer("🇺🇿 Введите название на **узбекском**:")

@router.message(AddProductStates.waiting_for_name_uz)
async def fsm_uz(message: Message, state: FSMContext):
    await state.update_data(name_uz=message.text)
    await state.set_state(AddProductStates.waiting_for_name_en)
    await message.answer("🇬🇧 Введите название на **английском**:")

@router.message(AddProductStates.waiting_for_name_en)
async def fsm_en(message: Message, state: FSMContext):
    await state.update_data(name_en=message.text)
    await state.set_state(AddProductStates.waiting_for_country)
    await message.answer("🌍 Укажите **страну происхождения** (Кения, Бразилия и т.д.):")

@router.message(AddProductStates.waiting_for_country)
async def fsm_country(message: Message, state: FSMContext):
    await state.update_data(country=message.text)
    await state.set_state(AddProductStates.waiting_for_method)
    kb = InlineKeyboardBuilder()
    kb.button(text="💧 Фильтр", callback_data="method_filter")
    kb.button(text="☕ Эспрессо", callback_data="method_espresso")
    kb.adjust(2)
    await message.answer("⚙️ Выберите метод обжарки:", reply_markup=kb.as_markup())

@router.callback_query(AddProductStates.waiting_for_method, F.data.startswith("method_"))
async def fsm_method(callback: CallbackQuery, state: FSMContext):
    await state.update_data(method=callback.data.split("_")[1])
    await state.set_state(AddProductStates.waiting_for_price_250g)
    await callback.message.answer("💰 Введите цену за **0.25 кг** (в сумах, например: `75000`):", parse_mode="Markdown")
    await callback.answer()

@router.message(AddProductStates.waiting_for_price_250g)
async def fsm_p250(message: Message, state: FSMContext):
    await state.update_data(price_250g=float(message.text.replace(" ", "")))
    await state.set_state(AddProductStates.waiting_for_price_500g)
    await message.answer("💰 Введите цену за **0.5 кг**:")

@router.message(AddProductStates.waiting_for_price_500g)
async def fsm_p500(message: Message, state: FSMContext):
    await state.update_data(price_500g=float(message.text.replace(" ", "")))
    await state.set_state(AddProductStates.waiting_for_price_1kg)
    await message.answer("💰 Введите цену за **1 кг**:")

@router.message(AddProductStates.waiting_for_price_1kg)
async def fsm_p1kg(message: Message, state: FSMContext):
    data = await state.get_data()
    price_1kg = float(message.text.replace(" ", ""))
    
    conn = sqlite3.connect("coffee_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO products (name_ru, name_uz, name_en, country, method, price_250g, price_500g, price_1kg, image_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (data["name_ru"], data["name_uz"], data["name_en"], data["country"], data["method"],
          data["price_250g"], data["price_500g"], price_1kg, data["photo_id"]))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("✅ **Лот успешно добавлен в базу и доступен в каталоге!**", parse_mode="Markdown")

dp.include_router(router)

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())