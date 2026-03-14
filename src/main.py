import requests
import json
import time
import sys
import os
import threading
import atexit
from dotenv import load_dotenv

from src.clients.xing_rest import XingRestTrader
from src.clients.gemini import GeminiAdvisor
from src.clients.xing_realtime import XingRealtimeClient
from src.clients.public_data import PublicDataClient
from src.clients.brave_search import BraveSearchClient
from src.utils.helpers import build_futures_cache

from src.services.alert_monitor import AlertMonitor
from src.services.scheduler import BotScheduler
from src.handlers.commands import CommandHandler
from src.handlers.nlp_router import NLPRouter

# --- Configuration ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "REPLACE_ME")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "REPLACE_ME")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

class BotContext:
    """Shared context passed to handlers and services"""
    def __init__(self):
        self.trader = None
        self.realtime_client = None
        self.public_data = None
        self.brave_client = None
        self.advisor = None
        self.alert_monitor = None
        self.scheduler = None

    def send_message(self, chat_id, text, parse_mode="Markdown"):
        try:
            url = f"{TELEGRAM_API_URL}/sendMessage"
            payload = {"chat_id": chat_id, "text": text}
            if parse_mode: payload["parse_mode"] = parse_mode
            res = requests.post(url, json=payload, timeout=15)
            data = res.json()
            if not data.get("ok"):
                print(f"⚠️ Telegram API Error: {data.get('description')}")
                if parse_mode is not None and "parse" in data.get("description", "").lower():
                    self.send_message(chat_id, text, parse_mode=None)
        except Exception as e:
            print(f"[Error] sending message: {e}")

bot_ctx = BotContext()
command_handler = None
nlp_router = None

def handle_incoming_message(chat_id, text):
    try:
        parts = text.split()
        if not parts: return
        cmd = parts[0].lower()
        print(f"[CMD] {cmd} | text={text[:60]}", flush=True)

        # 1. Try Deterministic Commands
        handled = command_handler.handle(chat_id, text, cmd, parts)
        
        # 2. Fallback to NLP Router
        if not handled:
            nlp_router.handle(chat_id, text)
            
    except Exception as e:
        import traceback; traceback.print_exc()
        try: bot_ctx.send_message(chat_id, f"치명적 오류: {e}")
        except: pass

def run_bot():
    offset = 0
    token_ok = TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN.strip() != "" and TELEGRAM_BOT_TOKEN != "REPLACE_ME"
    if not token_ok:
        print("ERROR: TELEGRAM_BOT_TOKEN not set. Add TELEGRAM_BOT_TOKEN=... to .env in project root.")
    else:
        try:
            r = requests.get(f"{TELEGRAM_API_URL}/getMe", timeout=10)
            if r.json().get("ok"): print(f"Telegram bot connected: @{r.json()['result'].get('username', '?')}")
        except Exception as e: print(f"Telegram connection check failed: {e}")
            
    print("Bot polling started...")
    error_consecutive_cnt = 0
    
    while True:
        try:
            payload = {"offset": offset, "timeout": 30, "allowed_updates": ["message"]}
            response = requests.post(f"{TELEGRAM_API_URL}/getUpdates", json=payload, timeout=40)
            data = response.json()
            
            if data.get("ok"):
                error_consecutive_cnt = 0
                for update in data.get("result", []):
                    update_id = update["update_id"]
                    if update_id >= offset: offset = update_id + 1
                    
                    if "message" in update and "text" in update["message"]:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"]["text"]
                        user = update["message"]["from"].get("username", "Unknown")
                        print(f"[Msg] {user}: {text}")
                        threading.Thread(target=handle_incoming_message, args=(chat_id, text)).start()
            else:
                error_code = data.get("error_code")
                error_consecutive_cnt += 1
                backoff_time = min(5 * (2 ** (error_consecutive_cnt - 1)), 600)
                if error_code == 409: print(f"⚠️ [409 Conflict] Another bot instance is stealing updates. Sleeping for {backoff_time}s...")
                else: print(f"⚠️ API Error backing off for {backoff_time}s...")
                time.sleep(backoff_time)
                
        except Exception as e:
            error_consecutive_cnt += 1
            backoff_time = min(5 * (2 ** (error_consecutive_cnt - 1)), 300)
            print(f"Polling Network Error: {e}. Retrying in {backoff_time}s...")
            time.sleep(backoff_time)

if __name__ == "__main__":
    _root = os.path.join(os.path.dirname(__file__), "..")
    _pid_file = os.path.abspath(os.path.join(_root, "spk_bot.pid"))
    try:
        with open(_pid_file, "w") as f: f.write(str(os.getpid()))
    except Exception: pass
    def _remove_pid():
        try:
            if os.path.exists(_pid_file): os.remove(_pid_file)
        except Exception: pass
    atexit.register(_remove_pid)

    # 1. Initialize API Clients into Context
    print("Initializing API Clients...", flush=True)
    bot_ctx.trader = XingRestTrader()
    bot_ctx.trader.get_access_token()
    build_futures_cache(bot_ctx.trader)
    
    bot_ctx.public_data = PublicDataClient()
    bot_ctx.brave_client = BraveSearchClient(api_key=BRAVE_API_KEY)
    bot_ctx.advisor = GeminiAdvisor(GEMINI_API_KEY)
    
    bot_ctx.realtime_client = XingRealtimeClient()
    bot_ctx.realtime_client.start()

    # 2. Initialize Services and Handlers
    print("Initializing Services...", flush=True)
    bot_ctx.alert_monitor = AlertMonitor(bot_ctx)
    bot_ctx.scheduler = BotScheduler(bot_ctx)
    command_handler = CommandHandler(bot_ctx)
    nlp_router = NLPRouter(bot_ctx)

    # 3. Start Background Threads
    print("Starting Background Threads...")
    threading.Thread(target=bot_ctx.alert_monitor.check_alerts_loop, daemon=True).start()
    threading.Thread(target=bot_ctx.alert_monitor.monitor_guidelines_loop, daemon=True).start()
    threading.Thread(target=bot_ctx.scheduler.run_schedule_loop, daemon=True).start()
    
    # 4. Phase 2: Start SPK Shared Data Server (Port 18791)
    try:
        from src.services.data_server import start_shared_data_server
        from src.utils.helpers import get_price_data
        print("Starting Shared Data Server for CoreBot (Port 18791)...")
        start_shared_data_server(lambda code: get_price_data(bot_ctx.trader, code), bot_ctx.trader.get_kospi200_futures_list, port=18791)
    except Exception as e:
        print(f"Failed to start Shared Data Server: {e}")
    
    # 5. Start Polling Loop
    run_bot()
