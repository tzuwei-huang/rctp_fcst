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
            BotCommand("t1", "獲取第一航廈未來 12 小時預報"),
            BotCommand("t1all", "獲取第一航廈至明日結束的所有預報"),
            BotCommand("t2", "獲取第二航廈未來 12 小時預報"),
            BotCommand("t2all", "獲取第二航廈至明日結束的所有預報"),
            BotCommand("help", "顯示說明文字"),
        ]
        await application.bot.set_my_commands(commands)
        logging.info("Bot commands registered.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display help message."""
        help_text = (
            "<b>桃園機場航班預報機器人</b>\n\n"
            "/t1 - 獲取第一航廈未來 12 小時預報\n"
            "/t1all - 獲取第一航廈至明日結束的預報\n"
            "/t2 - 獲取第二航廈未來 12 小時預報\n"
            "/t2all - 獲取第二航廈至明日結束的預報\n"
            "/help - 顯示此說明\n\n"
            "資料顯示為台北時間。"
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

    async def get_terminal_data(self, update: Update, terminal_key: str, show_all: bool = False):
        """Fetch and display terminal data. If show_all=True, shows until end of tomorrow."""
        now_taipei = datetime.datetime.now(TAIPEI_TZ)
        today = now_taipei.date()
        tomorrow = (now_taipei + datetime.timedelta(days=1)).date()
        
        all_records = []
        titles = []
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
            await update.message.reply_text("抱歉，目前無法從桃園機場官網獲獲取資料。")
            return

        # Filtering logic:
        final_list = []
        
        # If show_all=False, limit to 12 hours. If show_all=True, show everything until end of tomorrow.
        limit = 12 if not show_all else 48 
        
        for i in range(limit):
            target_dt = now_taipei + datetime.timedelta(hours=i)
            # Stop if we've reached the day after tomorrow
            if show_all and target_dt.date() > tomorrow:
                break
                
            target_hour = target_dt.hour
            target_date = target_dt.date()
            
            for r in all_records:
                if r['_date'] == target_date:
                    time_range = r.get('時間區間', '')
                    try:
                        record_hour = int(time_range.split(':')[0])
                        if record_hour == target_hour:
                            final_list.append(r)
                            break
                    except (ValueError, IndexError):
                        continue
        
        if not final_list:
            await update.message.reply_text("找不到對應時段的預報資料。")
            return

        # Format output
        display_title = titles[0] if titles else f"{terminal_key.upper()} 預報表"
        full_text_marker = " (完整)" if show_all else ""
        
        current_msg = f"<b>{display_title}{full_text_marker}</b>\n"
        current_msg += f"(台北時間：{now_taipei.strftime('%Y-%m-%d %H:%M')})\n"
        current_msg += "<pre>"
        current_msg += f"{'時間':<21} {'出境':<6} {'轉機':<6}\n"
        current_msg += "-" * 36 + "\n"
        
        for r in final_list:
            rec_date = r['_date']
            time_range = r.get('時間區間', '')
            
            # 格式化為 "MM/DD HH:00~HH:00"
            try:
                start_h = time_range.split(':')[0]
                end_h = f"{(int(start_h) + 1):02d}"
                display_time = f"{rec_date.strftime('%m/%d')} {start_h}:00~{end_h}:00"
            except:
                display_time = f"{rec_date.strftime('%m/%d')} {time_range}"
            
            out_count = r.get('出境桃園', 0)
            transfer_count = r.get('到站轉機', 0)
            line = f"{display_time:<21} {out_count:<6} {transfer_count:<6}\n"
            
            # Telegram has a limit of 4096 characters.
            if len(current_msg + line + "</pre>") > 4000:
                await update.message.reply_text(current_msg + "</pre>", parse_mode=ParseMode.HTML)
                current_msg = "<pre>"
            
            current_msg += line

        footer = "</pre>"
        if not show_all and len(final_list) < 12 and tomorrow not in available_dates:
            footer += f"\n<i>註：機場尚未發佈明日 ({tomorrow}) 的預報檔案。</i>"
        
        await update.message.reply_text(current_msg + footer, parse_mode=ParseMode.HTML)

    async def get_t1_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.get_terminal_data(update, "terminal_1", show_all=False)

    async def get_t1_all_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.get_terminal_data(update, "terminal_1", show_all=True)

    async def get_t2_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.get_terminal_data(update, "terminal_2", show_all=False)

    async def get_t2_all_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.get_terminal_data(update, "terminal_2", show_all=True)

    def run(self):
        application = ApplicationBuilder().token(self.token).post_init(self.post_init).build()
        
        application.add_handler(CommandHandler('t1', self.get_t1_data))
        application.add_handler(CommandHandler('t1all', self.get_t1_all_data))
        application.add_handler(CommandHandler('t2', self.get_t2_data))
        application.add_handler(CommandHandler('t2all', self.get_t2_all_data))
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
