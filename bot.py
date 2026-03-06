import os
import logging
import math
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ConversationHandler

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Константы
TOKEN = os.environ.get('TELEGRAM_TOKEN')
YOUR_NICK = '@Max_JDM_chel'

# Состояния диалога
PRICE, YEAR, ENGINE, POWER = range(4)

# Временное хранилище данных пользователя (в памяти)
user_data = {}

# ========== ФУНКЦИИ РАСЧЁТА (всё в Python) ==========

def calculate_duty(price_jpy, year, engine_cc, power_hp):
    """
    Рассчитывает все компоненты стоимости авто во Владивостоке.
    Возвращает словарь с результатами.
    """
    # Курсы валют (можно брать из интернета, но пока фиксированные для простоты)
    # В идеале получать курс из ЦБ, но для начала зададим приближённые
    jpy_rate = 0.55  # 1 JPY = 0.55 RUB (примерно)
    eur_rate = 95.0   # 1 EUR = 95 RUB

    # Возраст авто
    current_year = datetime.now().year
    age = current_year - year

    # Таможенная стоимость = цена в йенах + фрахт (120000 JPY)
    price_rub = price_jpy * jpy_rate
    freight_rub = 120000 * jpy_rate
    customs_value = price_rub + freight_rub

    # Расчёт пошлины
    if age < 3:
        # Для авто до 3 лет: максимум из (54% от стоимости, но не менее 2.5 евро/см³)
        duty_option1 = customs_value * 0.54
        duty_option2 = engine_cc * 2.5 * eur_rate
        duty_rub = max(duty_option1, duty_option2)
    elif age <= 5:
        # 3-5 лет: ставка по объёму
        if engine_cc <= 1000:
            rate_eur = 1.5
        elif engine_cc <= 1500:
            rate_eur = 1.7
        elif engine_cc <= 1800:
            rate_eur = 2.5
        elif engine_cc <= 2300:
            rate_eur = 2.7
        elif engine_cc <= 3000:
            rate_eur = 3.0
        else:
            rate_eur = 3.6
        duty_rub = engine_cc * rate_eur * eur_rate
    else:
        # Старше 5 лет
        if engine_cc <= 1000:
            rate_eur = 3.0
        elif engine_cc <= 1500:
            rate_eur = 3.2
        elif engine_cc <= 1800:
            rate_eur = 3.5
        elif engine_cc <= 2300:
            rate_eur = 4.8
        elif engine_cc <= 3000:
            rate_eur = 5.0
        else:
            rate_eur = 5.7
        duty_rub = engine_cc * rate_eur * eur_rate

    # Утильсбор
    if power_hp <= 160:
        util_rub = 5200
    elif power_hp <= 200:
        util_rub = 8476
    elif power_hp <= 300:
        util_rub = 29796
    elif power_hp <= 400:
        util_rub = 64116
    elif power_hp <= 500:
        util_rub = 108472
    else:
        util_rub = 240136

    # Таможенный сбор (зависит от таможенной стоимости)
    if customs_value <= 200000:
        customs_fee = 775
    elif customs_value <= 450000:
        customs_fee = 1550
    elif customs_value <= 1200000:
        customs_fee = 3100
    elif customs_value <= 2700000:
        customs_fee = 8530
    else:
        customs_fee = 13110

    # Услуги (ЭПТС, прописка, комиссия)
    services = 60000   # комплекс услуг
    propiska = 5000    # прописка (если нужна)
    commission = 30000 # твоя комиссия

    # НДС 20% (на таможенную стоимость + пошлину)
    nds = (customs_value + duty_rub) * 0.2

    # ИТОГО во Владивостоке (без комиссии)
    total_vladivostok = customs_value + duty_rub + util_rub + customs_fee + services + propiska + nds
    # ИТОГО с комиссией
    total_with_commission = total_vladivostok + commission

    return {
        'price_rub': round(price_rub),
        'freight_rub': round(freight_rub),
        'customs_value': round(customs_value),
        'duty_rub': round(duty_rub),
        'util_rub': round(util_rub),
        'customs_fee': round(customs_fee),
        'services': services,
        'propiska': propiska,
        'nds': round(nds),
        'commission': commission,
        'total_vlad': round(total_vladivostok),
        'total_with_commission': round(total_with_commission)
    }

def format_number(num):
    """Форматирование числа с пробелами (например, 1 000 000)"""
    return f"{num:,}".replace(',', ' ')

# ========== ЛОГИРОВАНИЕ В GOOGLE SHEETS (опционально) ==========

def log_to_google_sheets(data, results):
    """Запись результата в лист 'Логи' Google Sheets"""
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        gc = gspread.service_account(filename='credentials.json')
        sh = gc.open_by_key(os.environ.get('GOOGLE_SHEETS_ID'))
        worksheet = sh.worksheet('Логи')

        now = datetime.now()
        worksheet.append_row([
            now.strftime('%d.%m.%Y'),
            now.strftime('%H:%M:%S'),
            'бот',
            data.get('username', '-'),
            data['price'],
            data['year'],
            data['engine'],
            data['power'],
            results['total_with_commission'],
            results['duty_rub'],
            results['util_rub'],
            results['customs_fee'],
            results['services'],
            results['propiska'],
            results['commission']
        ])
        logger.info("✅ Данные записаны в Google Sheets")
    except Exception as e:
        logger.error(f"❌ Ошибка записи в Google Sheets: {e}")

# ========== ОБРАБОТЧИКИ КОМАНД ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚗 **Добро пожаловать в калькулятор авто из Японии!**\n\n"
        "Я помогу рассчитать полную стоимость автомобиля с доставкой во Владивосток.\n\n"
        "📌 **Введите стоимость авто в йенах** (например: 1000000):",
        parse_mode='Markdown'
    )
    return PRICE

async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip().replace(' ', '')
    try:
        price = int(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректную цену (целое положительное число):")
        return PRICE

    context.user_data['price'] = price
    await update.message.reply_text("📅 **Введите год выпуска** (например: 2020):", parse_mode='Markdown')
    return YEAR

async def handle_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        year = int(text)
        current_year = datetime.now().year
        if year < 1990 or year > current_year + 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"❌ Введите корректный год (1990-{current_year + 1}):")
        return YEAR

    context.user_data['year'] = year
    await update.message.reply_text("🔧 **Введите объём двигателя** в см³ (например: 1600):", parse_mode='Markdown')
    return ENGINE

async def handle_engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(' ', '')
    try:
        engine = int(text)
        if engine < 100 or engine > 10000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректный объём (100-10000 см³):")
        return ENGINE

    context.user_data['engine'] = engine
    await update.message.reply_text("⚡ **Введите мощность** в л.с. (например: 100):", parse_mode='Markdown')
    return POWER

async def handle_power(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        power = int(text)
        if power < 10 or power > 1000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректную мощность (10-1000 л.с.):")
        return POWER

    # Сохраняем мощность
    context.user_data['power'] = power

    # Получаем все данные
    price = context.user_data['price']
    year = context.user_data['year']
    engine = context.user_data['engine']

    # Выполняем расчёт
    await update.message.reply_text("⏳ Выполняю расчёт...")

    results = calculate_duty(price, year, engine, power)

    # Сохраняем результаты в context для кнопок
    context.user_data['last_results'] = results

    # Краткий результат
    short = (
        f"🚗 **РАСЧЁТ СТОИМОСТИ АВТО ИЗ ЯПОНИИ**\n\n"
        f"✅ **Ваши данные:**\n"
        f"• Цена: {format_number(price)} ¥\n"
        f"• Год: {year}\n"
        f"• Объём: {format_number(engine)} см³\n"
        f"• Мощность: {power} л.с.\n\n"
        f"💰 **ИТОГО во Владивостоке:** {format_number(results['total_with_commission'])} ₽\n\n"
        f"ℹ️ Нажмите кнопку **\"🔍 Детали\"**, чтобы увидеть полный расчёт"
    )

    # Кнопки
    keyboard = [
        [
            InlineKeyboardButton("🔍 Детали", callback_data='details'),
            InlineKeyboardButton("🔄 Новый расчёт", callback_data='new')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(short, reply_markup=reply_markup, parse_mode='Markdown')

    # Пытаемся записать в Google Sheets (если есть ключи)
    if os.environ.get('GOOGLE_SHEETS_ID') and os.path.exists('credentials.json'):
        log_data = {
            'username': update.effective_user.username,
            'price': price,
            'year': year,
            'engine': engine,
            'power': power
        }
        log_to_google_sheets(log_data, results)

    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'details':
        results = context.user_data.get('last_results')
        if results:
            full = (
                f"📊 **ДЕТАЛЬНЫЙ РАСЧЁТ:**\n\n"
                f"📦 Таможенная стоимость: {format_number(results['customs_value'])} ₽\n"
                f"📈 Пошлина: {format_number(results['duty_rub'])} ₽\n"
                f"🧾 Утильсбор: {format_number(results['util_rub'])} ₽\n"
                f"🏷️ Таможенный сбор: {format_number(results['customs_fee'])} ₽\n"
                f"📋 ЭПТС / услуги: {format_number(results['services'])} ₽\n"
                f"📍 Прописка: {format_number(results['propiska'])} ₽\n"
                f"💰 НДС 20%: {format_number(results['nds'])} ₽\n"
                f"➕ Комиссия: {format_number(results['commission'])} ₽\n\n"
                f"✨ **ИТОГО: {format_number(results['total_with_commission'])} ₽**"
            )
            await query.message.reply_text(full, parse_mode='Markdown')
        else:
            await query.message.reply_text("❌ Данные расчёта не найдены. Сделайте новый расчёт.")

    elif query.data == 'new':
        await query.message.reply_text("🚗 **Введите стоимость авто в йенах** (например: 1000000):", parse_mode='Markdown')
        return PRICE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Операция отменена. Для начала введите /start")
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "ℹ️ **Как пользоваться ботом:**\n\n"
        "1. Введите /start\n"
        "2. Последовательно введите:\n"
        "   • Цену авто в йенах\n"
        "   • Год выпуска\n"
        "   • Объём двигателя (см³)\n"
        "   • Мощность (л.с.)\n\n"
        "3. Получите расчёт с кнопками:\n"
        "   • 🔍 Детали — полная разбивка\n"
        "   • 🔄 Новый расчёт — начать заново"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ========== ЗАПУСК ==========

def main():
    if not TOKEN:
        logger.error("❌ Нет TELEGRAM_TOKEN!")
        return

    # Проверяем, есть ли ID таблицы (необязательно)
    if not os.environ.get('GOOGLE_SHEETS_ID'):
        logger.warning("⚠️ GOOGLE_SHEETS_ID не задан, логирование в таблицу отключено")

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price)],
            YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_year)],
            ENGINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_engine)],
            POWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_power)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("✅ Бот запущен. Жду сообщения...")
    app.run_polling()

if __name__ == '__main__':
    main()
