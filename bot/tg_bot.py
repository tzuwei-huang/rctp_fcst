import os
import sys
import datetime
import json
import logging
import pytz

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

TAIPEI_TZ = pytz.timezone('Asia/Taipei')

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
        logging.info("Bot commands registered.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display help message."""
        help_text = (
            "<b>桃園機場航班人次預報 Bot</b>\n\n"
            "/t1 - 獲取第一航廈最新出境與過境預報\n"
            "/t2 - 獲取第二航廈最新出境與過境預報\n"
            "/help - 顯示此說明\n\n"
            "資料顯示為台北時間，從現在開始往後顯示最多 12 小時。"
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

    def _get_file_for_date(self, target_date: datetime.date):
        """Helper to try getting a file for a specific date (with fallback)."""
        date_str = target_date.strftime("%Y_%m_%d")
        
        # Try _update first
        filename = f"{date_str}_update.json"
        url = f"https://www.taoyuan-airport.com/uploads/fos/{date_str}_update.xls"
        file_path = self.downloader.download_and_store_as_json(url, filename, verify=False)
        
        # Fallback to base
        if not file_path:
            filename = f"{date_str}.json"
            url = f"https://www.taoyuan-airport.com/uploads/fos/{date_str}.xls"
            file_path = self.downloader.download_and_store_as_json(url, filename, verify=False)
            
        return file_path

    async def get_terminal_data(self, update: Update, terminal_key: str):
        """Fetch and display terminal data for the next 12 hours (Taipei time)."""
        now_taipei = datetime.datetime.now(TAIPEI_TZ)
        
        # Dates to check: today and tomorrow
        today = now_taipei.date()
        tomorrow = (now_taipei + datetime.timedelta(days=1)).date()
        
        all_records = []
        titles = []
        
        # Track which dates we successfully got data for
        available_dates = []

        for d in [today, tomorrow]:
            file_path = self._get_file_for_date(d)
            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        day_data = json.load(f)
                        term_data = day_data.get('data', {}).get(terminal_key, {})
                        day_records = term_data.get('records', [])
                        if day_records:
                            available_dates.append(d)
                            for r in day_records:
                                r['_date'] = d
                                all_records.append(r)
                            if term_data.get('title'):
                                titles.append(term_data['title'])
                except Exception as e:
                    logging.error(f"Error reading JSON for {d}: {e}")

        if not all_records:
            await update.message.reply_text("抱歉，目前無法從桃園機場官網獲取資料。")
            return

        # Filtering logic:
        final_list = []
        for i in range(12):
            target_dt = now_taipei + datetime.timedelta(hours=i)
            target_hour = target_dt.hour
            target_date = target_dt.date()
            
            # Find the record for this target_date and hour
            for r in all_records:
                if r['_date'] == target_date:
                    time_range = r.get('時間區間', '')
                    # Format is "HH:00 ~ HH:59"
                    try:
                        record_hour = int(time_range.split(':')[0])
                        if record_hour == target_hour:
                            final_list.append(r)
                            break
                    except (ValueError, IndexError):
                        continue
        
        if not final_list:
            await update.message.reply_text("找不到當前時段往後的預報資料。")
            return

        # Format output
        display_title = titles[0] if titles else f"{terminal_key.upper()} 預報表"
        
        message = f"<b>{display_title}</b>\n"
        message += "<pre>"
        message += f"{'時間':<14} {'出境':<7} {'過境':<6}\n"
        message += "-" * 30 + "\n"
        
        for r in final_list:
            rec_date = r['_date']
            time_range = r.get('時間區間', '')
            # 取出起始時間 (例如 "22:00")
            start_time = time_range.split(' ~ ')[0] if ' ~ ' in time_range else time_range
            
            display_time = f"{rec_date.strftime('%m/%d')} {start_time}"
            
            out_count = r.get('出境桃園', 0)
            transfer_count = r.get('到站轉機', 0)
            message += f"{display_time:<15} {out_count:<8} {transfer_count:<6}\n"
        
        message += "</pre>"
        
        # Info about missing data if we couldn't get the full 12 hours
        if len(final_list) < 12:
            if tomorrow not in available_dates:
                message += f"\n<i>註：機場尚未發佈明日 ({tomorrow}) 的預報檔案。</i>"
            
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
        
        print("Bot is running (Taipei Time Locked)... Press Ctrl+C to stop.")
        application.run_polling()

if __name__ == "__main__":
    # Get token from environment variable or .env
    load_dotenv()
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("Please set the TELEGRAM_BOT_TOKEN environment variable.")
    else:
        bot = TelegramBot(TOKEN)
        bot.run()
