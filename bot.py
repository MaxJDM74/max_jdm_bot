#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_SHEETS_ID = os.environ.get('GOOGLE_SHEETS_ID')
YOUR_NICK = '@Max_JDM_chel'

# Состояния для диалога
PRICE, YEAR, ENGINE, POWER = range(4)

# ========== РАБОТА С GOOGLE SHEETS ==========

def get_google_sheets_client():
    """Подключение к Google Sheets через Service Account"""
    try:
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
    """Отправляем данные в Google Sheets и получаем расчёт"""
    try:
        client = get_google_sheets_client()
        if not client:
            return None, "❌ Ошибка подключения к таблице"
        
        sheet = client.open_by_key(GOOGLE_SHEETS_ID).worksheet('Калькулятор')
        
        # Записываем данные
        sheet.update('C5', [[price]])
        sheet.update('C6', [[year]])
        sheet.update('C7', [[engine]])
        sheet.update('C8', [[power]])
        
        import time
        time.sleep(1)
        
        # Читаем результаты
        total = sheet.acell('C28').value
        duty = sheet.acell('C19').value
        util = sheet.acell('C23').value
        customs_fee = sheet.acell('C21').value
        services = sheet.acell('C24').value
        propiska = sheet.acell('C25').value
        
        results = {
            'total': float(total) if total else 0,
            'duty': float(duty) if duty else 0,
            'util': float(util) if util else 0,
            'customs_fee': float(customs_fee) if customs_fee else 0,
            'services': float(services) if services else 60000,
            'propiska': float(propiska) if propiska else 5000
        }
        
        # Сохраняем в логи
        try:
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
                30000
            ])
        except:
            pass  # Если нет листа Логи - игнорируем
        
        return results, None
        
    except Exception as e:
        logger.error(f"Ошибка при расчёте: {e}")
        return None, f"❌ Ошибка расчёта: {str(e)}"

# ========== ФУНКЦИИ ДЛЯ ФОРМАТИРОВАНИЯ ==========

def format_number(num):
    """Форматирует число с пробелами"""
    return f"{int(num):,}".replace(',', ' ')

# ========== ОБРАБОТЧИКИ КОМАНД ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "🚗 **Добро пожаловать в калькулятор авто из Японии!**\n\n"
        "Я помогу рассчитать полную стоимость автомобиля с доставкой во Владивосток.\n\n"
        "📌 **Введите стоимость авто в йенах** (например: 1000000):"
    )
    return PRICE

async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода цены"""
    text = update.message.text.strip().replace(' ', '')
    
    try:
        price = int(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректную цену (целое положительное число):")
        return PRICE
    
    context.user_data['price'] = price
    await update.message.reply_text("📅 **Введите год выпуска** (например: 2020):")
    return YEAR

async def handle_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода года"""
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
    await update.message.reply_text("🔧 **Введите объём двигателя** в см³ (например: 1600):")
    return ENGINE

async def handle_engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода объёма"""
    text = update.message.text.strip().replace(' ', '')
    
    try:
        engine = int(text)
        if engine < 100 or engine > 10000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректный объём (100-10000 см³):")
        return ENGINE
    
    context.user_data['engine'] = engine
    await update.message.reply_text("⚡ **Введите мощность** в л.с. (например: 100):")
    return POWER

async def handle_power(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода мощности и расчёт"""
    text = update.message.text.strip()
    
    try:
        power = int(text)
        if power < 10 or power > 1000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите корректную мощность (10-1000 л.с.):")
        return POWER
    
    price = context.user_data.get('price')
    year = context.user_data.get('year')
    engine = context.user_data.get('engine')
    
    if not all([price, year, engine]):
        await update.message.reply_text("❌ Ошибка данных. Начните заново с /start")
        return ConversationHandler.END
    
    await update.message.reply_text("⏳ Выполняю расчёт...")
    
    results, error = calculate_in_sheets(price, year, engine, power)
    
    if error:
        await update.message.reply_text(error)
        return ConversationHandler.END
    
    context.user_data['last_results'] = results
    
    # Формируем краткий результат
    short_result = (
        f"🚗 **РАСЧЁТ СТОИМОСТИ АВТО ИЗ ЯПОНИИ**\n\n"
        f"✅ **Ваши данные:**\n"
        f"• Цена: {format_number(price)} ¥\n"
        f"• Год: {year}\n"
        f"• Объём: {format_number(engine)} см³\n"
        f"• Мощность: {power} л.с.\n\n"
        f"💰 **ИТОГО во Владивостоке:** {format_number(results['total'])} ₽\n\n"
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
    
    await update.message.reply_text(short_result, reply_markup=reply_markup)
    
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'details':
        results = context.user_data.get('last_results')
        if results:
            full_result = (
                f"📊 **ДЕТАЛЬНЫЙ РАСЧЁТ:**\n\n"
                f"📈 Пошлина: {format_number(results['duty'])} ₽\n"
                f"🧾 Утильсбор: {format_number(results['util'])} ₽\n"
                f"🏷️ Таможенный сбор: {format_number(results['customs_fee'])} ₽\n"
                f"📋 ЭПТС / услуги: {format_number(results['services'])} ₽\n"
                f"📍 Прописка: {format_number(results['propiska'])} ₽\n"
                f"➕ Комиссия: 30 000 ₽\n\n"
                f"💰 **ИТОГО: {format_number(results['total'])} ₽**"
            )
            await query.message.reply_text(full_result)
        else:
            await query.message.reply_text("❌ Данные расчёта не найдены. Сделайте новый расчёт.")
    
    elif query.data == 'new':
        await query.message.reply_text("🚗 **Введите стоимость авто в йенах** (например: 1000000):")
        return PRICE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
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
    await update.message.reply_text(help_text)

# ========== ЗАПУСК БОТА ==========

def main():
    """Главная функция запуска бота"""
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не задан!")
        return
    
    if not GOOGLE_SHEETS_ID:
        logger.error("❌ GOOGLE_SHEETS_ID не задан!")
        return
    
    # Создаём приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
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
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("✅ Бот запущен и работает в режиме polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
