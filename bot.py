import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ.get('TELEGRAM_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('🚗 Привет! Я живой. Отправь любое сообщение.')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f'🔥 Ты написал: {update.message.text}')

def main():
    if not TOKEN:
        print("❌ Нет токена!")
        return
    
    print("✅ Запускаю бота...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    print("✅ Бот запущен. Жду сообщения...")
    app.run_polling()

if __name__ == '__main__':
    main()