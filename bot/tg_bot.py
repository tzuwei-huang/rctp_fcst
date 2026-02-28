import os
import sys
import datetime
import json
import logging

from dotenv import load_dotenv
from telegram import Update
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
        self.downloader = FileDownloader(download_dir="test_downloads")

    async def get_t2_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fetch and display newest T2 data."""
        date_str = datetime.datetime.now().strftime("%Y_%m_%d")
        filename = f"{date_str}_update.json"
        url = f"https://www.taoyuan-airport.com/uploads/fos/{date_str}_update.xls"
        
        file_path = os.path.join("test_downloads", filename)
        
        # Download if not exists or if it's been an hour (simplified check)
        # For simplicity, we just download it on every command in this example, 
        # but in production, you might want to cache it.
        file_path = self.downloader.download_and_store_as_json(url, filename, verify=False)
        
        if not file_path or not os.path.exists(file_path):
            await update.message.reply_text("抱歉，無法獲取目前的資料。")
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        t2_table = data.get('data', {}).get('terminal_2', {})
        records = t2_table.get('records', [])
        title = t2_table.get('title', "第二航廈預報表")

        if not records:
            await update.message.reply_text(f"找不到 {title} 的資料。")
            return

        # Format as a simple table (showing first few relevant columns for readability)
        message = f"<b>{title}</b>\n"
        message += "<pre>"
        message += f"{'時間':<15} {'入境':<5} {'出境':<5} {'合計':<5}\n"
        message += "-" * 35 + "\n"
        
        # Show upcoming hours (up to 10 rows for brevity)
        now_hour = datetime.datetime.now().hour
        count = 0
        for r in records:
            # Simple check to show current and future hours
            time_str = r.get('時間區間', '')
            try:
                hour = int(time_str.split(':')[0])
                if hour >= now_hour:
                    in_count = r.get('入境桃園', 0)
                    out_count = r.get('出境桃園', 0)
                    total = r.get('合計', 0)
                    message += f"{time_str:<15} {in_count:<5} {out_count:<5} {total:<5}\n"
                    count += 1
                if count >= 10: break
            except:
                continue
        
        message += "</pre>"
        
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

    def run(self):
        application = ApplicationBuilder().token(self.token).build()
        
        t2_handler = CommandHandler('t2', self.get_t2_data)
        application.add_handler(t2_handler)
        
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
