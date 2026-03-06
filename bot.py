import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import gspread
from google.oauth2.service_account import Credentials
import subprocess
try:
    subprocess.run(['ntpdate', '-u', 'pool.ntp.org'], check=False)
except:
    pass
# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')
SHEET_ID = os.environ.get('GOOGLE_SHEETS_ID')

# ========== РАБОТА С GOOGLE SHEETS ==========

def test_sheet_connection():
    """Проверка связи с таблицей"""
    try:
        # Используем современный метод service_account
        # Он сам читает credentials.json и сам берет нужные scopes
        gc = gspread.service_account(filename='credentials.json')
        
        # Открываем таблицу по ID
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet('Калькулятор')
        
        # Читаем ячейку C1 (курс JPY)
        value = worksheet.acell('C1').value
        
        return True, f"✅ Связь есть! Курс JPY: {value}"
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return False, f"❌ Ошибка: {str(e)}"

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
    await update.message.reply_text(message)

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

