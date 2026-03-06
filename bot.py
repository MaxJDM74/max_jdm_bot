import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import gspread
from google.oauth2.service_account import Credentials
import subprocess
import logging

# Принудительная синхронизация времени сервера
try:
    subprocess.run(['ntpdate', '-u', 'pool.ntp.org'], check=False, capture_output=True)
    logging.info("✅ Время сервера синхронизировано")
except Exception as e:
    logging.warning(f"⚠️ Не удалось синхронизировать время: {e}")
# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
SHEET_ID = os.environ.get('GOOGLE_SHEETS_ID')

# ========== РАБОТА С GOOGLE SHEETS ==========

def get_sheets_client():
    """Подключение к Google Sheets с синхронизацией времени и правильными scopes"""
    # 1. Пытаемся синхронизировать время
    try:
        import subprocess
        subprocess.run(['ntpdate', '-u', 'pool.ntp.org'], check=False, capture_output=True)
        logging.info("✅ Время синхронизировано")
    except Exception as e:
        logging.warning(f"⚠️ Не удалось синхронизировать время: {e}")

    # 2. Подключаемся с правильными scopes
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        # Правильный и полный набор scopes
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/spreadsheets'
        ]

        # Загружаем credentials из файла
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            'credentials.json',
            scope
        )

        client = gspread.authorize(credentials)
        logging.info("✅ Подключение к Google Sheets успешно")
        return client
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к Google Sheets: {e}")
        return None
def test_sheet_connection():
    """Тест подключения к таблице"""
    try:
        client = get_sheets_client()
        if not client:
            return False, "Не удалось подключиться к Google Sheets"
        
        sheet = client.open_by_key(SHEET_ID).worksheet('Калькулятор')
        value = sheet.acell('C1').value  # Берём курс JPY для проверки
        
        return True, f"Связь есть! Курс JPY: {value}"
    except Exception as e:
        logger.error(f"Ошибка при тесте таблицы: {e}")
        return False, f"Ошибка: {str(e)}"

# ========== ОБРАБОТЧИКИ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🚗 Привет! Я живой.\n'
        'Команды:\n'
        '/test_sheets - проверить связь с таблицей\n'
        '/start - это меню'
    )

async def test_sheets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Проверяю связь с таблицей...")
    
    success, message = test_sheet_connection()
    
    if success:
        await update.message.reply_text(f"✅ {message}")
    else:
        await update.message.reply_text(f"❌ {message}")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f'🔥 Ты написал: {update.message.text}')

# ========== ЗАПУСК ==========

def main():
    if not TOKEN:
        logger.error("❌ Нет TELEGRAM_TOKEN!")
        return
    
    if not SHEET_ID:
        logger.error("❌ Нет GOOGLE_SHEETS_ID!")
        return
    
    logger.info("✅ Запускаю бота...")
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('test_sheets', test_sheets))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    logger.info("✅ Бот запущен. Жду сообщения...")
    app.run_polling()

if __name__ == '__main__':
    main()



