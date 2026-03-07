import os
import logging
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, ConversationHandler
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TOKEN = os.environ.get('TELEGRAM_TOKEN')
YOUR_NICK = '@Max_JDM_chel'

# Состояния диалога
PRICE, YEAR, ENGINE, POWER = range(4)

# ========== ПОЛУЧЕНИЕ АКТУАЛЬНЫХ КУРСОВ ==========
def get_currency_rates():
    """Получает актуальные курсы с сайта ЦБ РФ"""
    try:
        response = requests.get('https://www.cbr-xml-daily.ru/daily_json.js', timeout=5)
        data = response.json()
        # Курс йены (за 100 йен, делим на 100)
        jpy_rate = data['Valute']['JPY']['Value'] / 100
        eur_rate = data['Valute']['EUR']['Value']
        logger.info(f"✅ Получены курсы: JPY={jpy_rate:.4f}, EUR={eur_rate:.4f}")
        return {'jpy': round(jpy_rate, 4), 'eur': round(eur_rate, 4)}
    except Exception as e:
        logger.error(f"❌ Ошибка получения курсов: {e}")
        # Запасные курсы на случай ошибки
        return {'jpy': 0.55, 'eur': 95.0}

# ========== ФУНКЦИИ РАСЧЁТА (БЕЗ НДС) ==========
def calculate_duty(price_jpy, year, engine_cc, power_hp):
    rates = get_currency_rates()
    jpy_rate, eur_rate = rates['jpy'], rates['eur']

    current_year = datetime.now().year
    age = current_year - year

    # Таможенная стоимость = авто + фрахт (120 000 йен)
    price_rub = price_jpy * jpy_rate * 1,05
    freight_rub = 120000 * jpy_rate * 1,05
    customs_value = price_rub + freight_rub

    # Расчёт пошлины
    if age < 3:
        duty_option1 = customs_value * 0.54
        duty_option2 = engine_cc * 2.5 * eur_rate
        duty_rub = max(duty_option1, duty_option2)
    elif age <= 5:
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

    # Таможенный сбор
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

    # Фиксированные услуги
    services = 60000
    propiska = 5000
    commission = 30000

    # ИТОГО
    total_vlad = customs_value + duty_rub + util_rub + customs_fee + services + propiska
    total_with_commission = total_vlad + commission

    return {
        'customs_value': round(customs_value),
        'duty_rub': round(duty_rub),
        'util_rub': round(util_rub),
        'customs_fee': round(customs_fee),
        'services': services,
        'propiska': propiska,
        'commission': commission,
        'total_with_commission': round(total_with_commission),
        'jpy_rate': jpy_rate,
        'eur_rate': eur_rate
    }

def format_number(num):
    return f"{num:,}".replace(',', ' ')

# ========== ЛОГИРОВАНИЕ ЗАПРОСОВ ==========
def log_request(user_id, username, data, results):
    logger.info("=" * 50)
    logger.info(f"👤 Пользователь: {username} (ID: {user_id})")
    logger.info(f"📅 Дата/время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    logger.info(f"📊 Входные данные: {data['price']} JPY, {data['year']} г., {data['engine']} см³, {data['power']} л.с.")
    logger.info(f"💰 Результат: {results['total_with_commission']} ₽ (с комиссией)")
    logger.info(f"💱 Курсы: JPY={results['jpy_rate']} ₽, EUR={results['eur_rate']} ₽")
    logger.info("=" * 50)

# ========== ОБРАБОТЧИКИ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"🟢 Пользователь {user.username or 'без username'} (ID: {user.id}) запустил бота")
    await update.message.reply_text(
        "🚗 **Добро пожаловать в калькулятор авто из Японии!**\n\n"
        "Я помогу рассчитать полную стоимость автомобиля с доставкой во Владивосток.\n\n"
        "📌 **Введите стоимость авто в йенах** (например: 1000000):",
        parse_mode='Markdown'
    )
    return PRICE

async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    context.user_data['power'] = power
    price = context.user_data['price']
    year = context.user_data['year']
    engine = context.user_data['engine']

    await update.message.reply_text("⏳ Выполняю расчёт...")
    results = calculate_duty(price, year, engine, power)
    context.user_data['last_results'] = results

    # Логируем запрос
    log_data = {'price': price, 'year': year, 'engine': engine, 'power': power}
    log_request(update.effective_user.id, update.effective_user.username, log_data, results)

    # Краткий результат
    short = (
        f"🚗 **РАСЧЁТ СТОИМОСТИ АВТО ИЗ ЯПОНИИ**\n\n"
        f"✅ **Ваши данные:**\n"
        f"• Цена: {format_number(price)} ¥\n"
        f"• Год: {year}\n"
        f"• Объём: {format_number(engine)} см³\n"
        f"• Мощность: {power} л.с.\n\n"
        f"💱 **Курсы на сегодня:**\n"
        f"• 1 JPY = {results['jpy_rate']} ₽\n"
        f"• 1 EUR = {results['eur_rate']} ₽\n\n"
        f"💰 **ИТОГО во Владивостоке:** {format_number(results['total_with_commission'])} ₽\n"
    )

    # Клавиатура с двумя кнопками
    keyboard = [
        [
            InlineKeyboardButton("🔍 Детали", callback_data='details'),
            InlineKeyboardButton("🔄 Новый расчёт", callback_data='new')
        ]
    ]
    await update.message.reply_text(
        short,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'details':
        results = context.user_data.get('last_results')
        if results:
            full = (
                f"📊 **ДЕТАЛЬНЫЙ РАСЧЁТ:**\n\n"
                f"📦 Таможенная стоимость = авто + фрахт (120 000 йен): {format_number(results['customs_value'])} ₽\n"
                f"📈 Пошлина: {format_number(results['duty_rub'])} ₽\n"
                f"🧾 Утильсбор: {format_number(results['util_rub'])} ₽\n"
                f"🏷️ Таможенный сбор: {format_number(results['customs_fee'])} ₽\n"
                f"📋 ЭПТС / услуги: {format_number(results['services'])} ₽\n"
                f"📍 Прописка: {format_number(results['propiska'])} ₽\n"
                f"➕ Комиссия: {format_number(results['commission'])} ₽\n\n"
                f"💱 Курсы: JPY={results['jpy_rate']} ₽, EUR={results['eur_rate']} ₽\n\n"
                f"✨ **ИТОГО: {format_number(results['total_with_commission'])} ₽**"
            )
            # Добавляем кнопку "Новый расчёт" прямо под деталями
            await query.message.reply_text(
                full,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Новый расчёт", callback_data='new')]]),
                parse_mode='Markdown'
            )
        else:
            await query.message.reply_text("❌ Данные не найдены. Введите /start для нового расчёта.")
    elif query.data == 'new':
        # Полностью очищаем данные пользователя
        context.user_data.clear()
        await query.message.reply_text(
            "🚗 **Введите стоимость авто в йенах** (например: 1000000):",
            parse_mode='Markdown'
        )
        return PRICE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено. Для начала введите /start")
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ **Как пользоваться ботом:**\n\n"
        "1. Введите /start\n"
        "2. Последовательно введите:\n"
        "   • Цену авто в йенах\n"
        "   • Год выпуска\n"
        "   • Объём двигателя (см³)\n"
        "   • Мощность (л.с.)\n\n"
        "3. Получите расчёт с кнопками.\n"
        "4. Для нового расчёта нажмите кнопку «🔄 Новый расчёт» в любом сообщении.",
        parse_mode='Markdown'
    )

# ========== ЗАПУСК ==========
def main():
    if not TOKEN:
        logger.error("❌ Нет TELEGRAM_TOKEN!")
        return

    app = Application.builder().token(TOKEN).build()

    # ConversationHandler с entry points: /start и callback_data='new'
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CallbackQueryHandler(button_callback, pattern='^new$')
        ],
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
    # Обработчик для кнопки 'details' (не входит в диалог)
    app.add_handler(CallbackQueryHandler(button_callback, pattern='^details$'))

    logger.info("✅ Бот запущен. Жду сообщения...")
    app.run_polling()

if __name__ == '__main__':
    main()

