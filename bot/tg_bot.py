import os
import sys
import datetime
import json
import logging

from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Add parent directory to path to import downloader
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from downloader import FileDownloader

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.downloader = FileDownloader(download_dir="Downloads")

    async def post_init(self, application):
        """Register commands with Telegram so they show up in the menu."""
        commands = [
            BotCommand("t1", "獲取第一航廈最新預報資料"),
            BotCommand("t2", "獲取第二航廈最新預報資料"),
            BotCommand("help", "顯示說明文字"),
        ]
        await application.bot.set_my_commands(commands)
        print("Bot commands registered.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display help message."""
        help_text = (
            "<b>桃園機場航班人次預報 Bot</b>\n\n"
            "/t1 - 獲取第一航廈最新出境與過境預報\n"
            "/t2 - 獲取第二航廈最新出境與過境預報\n"
            "/help - 顯示此說明"
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

    async def get_terminal_data(self, update: Update, terminal_key: str):
        """Generic method to fetch and display terminal data."""
        date_str = datetime.datetime.now().strftime("%Y_%m_%d")
        filename = f"{date_str}_update.json"
        url = f"https://www.taoyuan-airport.com/uploads/fos/{date_str}_update.xls"
        ""
        
        # Download and store
        file_path = self.downloader.download_and_store_as_json(url, filename, verify=False)
        
        if not file_path or not os.path.exists(file_path):
            await update.message.reply_text("抱歉，無法獲取目前的資料。")
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        table_data = data.get('data', {}).get(terminal_key, {})
        records = table_data.get('records', [])
        title = table_data.get('title', f"{terminal_key.upper()} 預報表")

        if not records:
            await update.message.reply_text(f"找不到 {title} 的資料。")
            return

        # Format as a simple table
        message = f"<b>{title}</b>\n"
        message += "<pre>"
        message += f"{'時間':<15} {'出境':<6} {'過境':<6}\n"
        message += "-" * 30 + "\n"
        
        now_hour = datetime.datetime.now().hour
        count = 0
        for r in records:
            time_str = r.get('時間區間', '')
            try:
                hour = int(time_str.split(':')[0])
                if hour >= now_hour:
                    out_count = r.get('出境桃園', 0)
                    transfer_count = r.get('到站轉機', 0)
                    message += f"{time_str:<15} {out_count:<6} {transfer_count:<6}\n"
                    count += 1
                if count >= 10: break
            except:
                continue
        
        message += "</pre>"
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

    async def get_t1_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.get_terminal_data(update, "terminal_1")

    async def get_t2_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.get_terminal_data(update, "terminal_2")

    def run(self):
        application = ApplicationBuilder().token(self.token).post_init(self.post_init).build()
        
        application.add_handler(CommandHandler('t1', self.get_t1_data))
        application.add_handler(CommandHandler('t2', self.get_t2_data))
        application.add_handler(CommandHandler('help', self.help_command))
        
        print("Bot is running... Press Ctrl+C to stop.")
        application.run_polling()

if __name__ == "__main__":
    # Get token from environment variable for security
    load_dotenv()
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("Please set the TELEGRAM_BOT_TOKEN environment variable.")
    else:
        bot = TelegramBot(TOKEN)
        bot.run()
