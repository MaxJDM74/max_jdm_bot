#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler, ContextTypes
import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GOOGLE_SHEETS_ID = os.getenv('GOOGLE_SHEETS_ID')
YOUR_NICK = '@Max_JDM_chel'  # Твой ник в Telegram

# Состояния для диалога
PRICE, YEAR, ENGINE, POWER = range(4)

# Данные пользователей (временное хранилище)
user_data = {}

# ========== РАБОТА С GOOGLE SHEETS ==========

def get_google_sheets_client():
    """Подключение к Google Sheets через Service Account"""
    try:
        # Загружаем credentials из файла
        creds = Credentials.from_service_account_file(
            'credentials.json',
            scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        )
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        logger.error(f"Ошибка подключения к Google Sheets: {e}")
        return None

def calculate_in_sheets(price, year, engine, power):
    """
    Отправляем данные в Google Sheets и получаем расчёт
    """
    try:
        client = get_google_sheets_client()
        if not client:
            return None, "❌ Ошибка подключения к таблице"
        
        # Открываем таблицу
        sheet = client.open_by_key(GOOGLE_SHEETS_ID).worksheet('Калькулятор')
        
        # Записываем данные в ячейки ввода
        sheet.update('C5', [[price]])  # Цена в йенах
        sheet.update('C6', [[year]])   # Год
        sheet.update('C7', [[engine]]) # Объём
        sheet.update('C8', [[power]])  # Мощность
        
        # Ждём пересчёта (небольшая задержка)
        import time
        time.sleep(1)
        
        # Читаем результаты
        total = sheet.acell('C28').value  # Итого с комиссией
        duty = sheet.acell('C19').value   # Пошлина
        util = sheet.acell('C23').value   # Утильсбор
        customs_fee = sheet.acell('C21').value  # Таможенный сбор
        services = sheet.acell('C24').value     # ЭПТС/услуги
        propiska = sheet.acell('C25').value     # Прописка
        
        # Формируем результаты
        results = {
            'total': float(total) if total else 0,
            'duty': float(duty) if duty else 0,
            'util': float(util) if util else 0,
            'customs_fee': float(customs_fee) if customs_fee else 0,
            'services': float(services) if services else 60000,
            'propiska': float(propiska) if propiska else 5000
        }
        
        # Сохраняем в логи
        log_sheet = client.open_by_key(GOOGLE_SHEETS_ID).worksheet('Логи')
        now = datetime.now()
        log_sheet.append_row([
            now.strftime('%d.%m.%Y'),
            now.strftime('%H:%M:%S'),
            'Python Bot',
            '-',
            price,
            year,
            engine,
            power,
            results['total'],
            results['duty'],
            results['util'],
            results['customs_fee'],
            results['services'],
            results['propiska'],
            30000  # комиссия
        ])
        
        return results, None
        
    except Exception as e:
        logger.error(f"Ошибка при расчёте: {e}")
        return None, f"❌ Ошибка расчёта: {str(e)}"

# ========== ФУНКЦИИ ДЛЯ ФОРМАТИРОВАНИЯ ==========

def format_number(num):
    """Форматирует число с пробелами"""
    return f"{int(num):,}".replace(',', ' ')

def create_short_result(price, year, engine, power, total):
    """Создаёт краткий результат"""
    return (
        f"🚗 **РАСЧЁТ СТОИМОСТИ АВТО ИЗ ЯПОНИИ**\n\n"
        f"✅ **Ваши данные:**\n"
        f"• Цена: {format_number(price)} ¥\n"
        f"• Год: {year}\n"
        f"• Объём: {format_number(engine)} см³\n"
        f"• Мощность: {power} л.с.\n\n"
        f"💰 **ИТОГО во Владивостоке:** {format_number(total)} ₽\n\n"
        f"ℹ️ Нажмите кнопку **\"🔍 Детали\"**, чтобы увидеть полный расчёт"
    )

def create_full_result(results):
    """Создаёт полный результат"""
    return (
        f"📊 **ДЕТАЛЬНЫЙ РАСЧЁТ:**\n\n"
        f"📈 Пошлина: {format_number(results['duty'])} ₽\n"
        f"🧾 Утильсбор: {format_number(results['util'])} ₽\n"
        f"🏷️ Таможенный сбор: {format_number(results['customs_fee'])} ₽\n"
        f"📋 ЭПТС / услуги: {format_number(results['services'])} ₽\n"
        f"📍 Прописка: {format_number(results['propiska'])} ₽\n"
        f"➕ Комиссия: 30 000 ₽\n\n"
        f"💰 **ИТОГО: {format_number(results['total'])} ₽**"
    )

# ========== ОБРАБОТЧИКИ КОМАНД ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    chat_id = update.effective_chat.id
    
    # Очищаем предыдущие данные
    if chat_id in user_data:
        del user_data[chat_id]
    
    await update.message.reply_text(
        "🚗 **Добро пожаловать в калькулятор авто из Японии!**\n\n"
        "Я помогу рассчитать полную стоимость автомобиля с доставкой во Владивосток.\n\n"
        "📌 **Введите стоимость авто в йенах** (например: 1000000):"
    )
    
    return PRICE

async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода цены"""
    chat_id = update.effective_chat.id
    text = update.message.text.strip().replace(' ', '')
    
    try:
        price = int(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректную цену (целое положительное число):")
        return PRICE
    
    user_data[chat_id] = {'price': price}
    
    await update.message.reply_text("📅 **Введите год выпуска** (например: 2020):")
    return YEAR

async def handle_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода года"""
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    try:
        year = int(text)
        current_year = datetime.now().year
        if year < 1990 or year > current_year + 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"❌ Введите корректный год (1990-{current_year + 1}):")
        return YEAR
    
    user_data[chat_id]['year'] = year
    
    await update.message.reply_text("🔧 **Введите объём двигателя** в см³ (например: 1600):")
    return ENGINE

async def handle_engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода объёма"""
    chat_id = update.effective_chat.id
    text = update.message.text.strip().replace(' ', '')
    
    try:
        engine = int(text)
        if engine < 100 or engine > 10000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректный объём (100-10000 см³):")
        return ENGINE
    
    user_data[chat_id]['engine'] = engine
    
    await update.message.reply_text("⚡ **Введите мощность** в л.с. (например: 100):")
    return POWER

async def handle_power(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода мощности и расчёт"""
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    try:
        power = int(text)
        if power < 10 or power > 1000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректную мощность (10-1000 л.с.):")
        return POWER
    
    # Получаем все данные
    data = user_data.get(chat_id, {})
    price = data.get('price')
    year = data.get('year')
    engine = data.get('engine')
    
    if not all([price, year, engine]):
        await update.message.reply_text("❌ Ошибка данных. Начните заново с /start")
        return ConversationHandler.END
    
    # Отправляем сообщение о расчёте
    await update.message.reply_text("⏳ Выполняю расчёт...")
    
    # Получаем расчёт из Google Sheets
    results, error = calculate_in_sheets(price, year, engine, power)
    
    if error:
        await update.message.reply_text(error)
        return ConversationHandler.END
    
    # Сохраняем результаты для кнопки "Детали"
    context.user_data['last_results'] = results
    context.user_data['last_input'] = {
        'price': price,
        'year': year,
        'engine': engine,
        'power': power
    }
    
    # Создаём клавиатуру с кнопками
    keyboard = [
        [
            InlineKeyboardButton("🔍 Детали", callback_data='details'),
            InlineKeyboardButton("🔄 Новый расчёт", callback_data='new')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем краткий результат
    short_result = create_short_result(price, year, engine, power, results['total'])
    await update.message.reply_text(short_result, reply_markup=reply_markup, parse_mode='Markdown')
    
    # Очищаем временные данные
    if chat_id in user_data:
        del user_data[chat_id]
    
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'details':
        # Показываем детальный расчёт
        results = context.user_data.get('last_results')
        if results:
            full_result = create_full_result(results)
            await query.message.reply_text(full_result, parse_mode='Markdown')
        else:
            await query.message.reply_text("❌ Данные расчёта не найдены. Сделайте новый расчёт.")
    
    elif query.data == 'new':
        # Начинаем новый расчёт
        await query.message.reply_text("🚗 **Введите стоимость авто в йенах** (например: 1000000):")
        return PRICE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    chat_id = update.effective_chat.id
    if chat_id in user_data:
        del user_data[chat_id]
    await update.message.reply_text("❌ Операция отменена. Для начала введите /start")
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка"""
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

# ========== НАСТРОЙКА WEBHOOK ДЛЯ FLASK ==========

# Создаём Flask приложение
app = Flask(__name__)

# Глобальная переменная для приложения бота
telegram_app = None

def setup_bot():
    """Настройка и запуск бота"""
    global telegram_app
    
    # Создаём приложение бота
    telegram_app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )
    
    # Настраиваем ConversationHandler
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
    
    # Добавляем обработчики
    telegram_app.add_handler(conv_handler)
    telegram_app.add_handler(CommandHandler('help', help_command))
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    
    return telegram_app

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработчик вебхука от Telegram"""
    if telegram_app:
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        telegram_app.process_update(update)
    return jsonify({"ok": True})

@app.route('/')
def index():
    return "Бот работает! Используй /webhook для Telegram."

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Ручная установка вебхука"""
    if telegram_app:
        webhook_url = f"https://{request.host}/webhook"
        telegram_app.bot.set_webhook(url=webhook_url)
        return f"Webhook установлен на {webhook_url}"
    return "Бот не инициализирован"

@app.route('/delete_webhook', methods=['GET'])
def delete_webhook():
    """Удаление вебхука"""
    if telegram_app:
        telegram_app.bot.delete_webhook()
        return "Webhook удалён"
    return "Бот не инициализирован"

# ========== ЗАПУСК ==========

if __name__ == '__main__':
    print("✅ Бот запущен и работает в режиме polling...")
    application.run_polling()
    
    # Проверяем наличие credentials.json
    if not os.path.exists('credentials.json'):
        logger.error("❌ Файл credentials.json не найден! Получите его из Google Cloud Console")
        exit(1)
    
    logger.info("✅ Настройка бота...")
    setup_bot()
    
    # Запускаем Flask-сервер
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"✅ Бот запущен на порту {port}")

    app.run(host='0.0.0.0', port=port, debug=False)
