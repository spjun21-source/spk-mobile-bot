import os
import json
import time
import schedule
from src.utils.helpers import get_price_data
from src.clients.public_data import PublicDataClient

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "config")
SUBSCRIBERS_FILE = os.path.join(CONFIG_DIR, "subscribers.json")

class BotScheduler:
    def __init__(self, bot_context):
        self.bot = bot_context

    def load_subscribers(self):
        if not os.path.exists(SUBSCRIBERS_FILE): return {}
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
            
    def save_subscribers(self, subs):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
            json.dump(subs, f, ensure_ascii=False, indent=4)

    def job_morning_report(self, is_open=False):
        print(f"⏰ Running Scheduled Report (is_open={is_open})...")
        subs = self.load_subscribers()
        if not subs: return
        
        us_context = self.bot.brave_client.search("간밤 미국 증시 마감 요약 주요 지수 특징주") if self.bot.brave_client else "미국 증시 정보 없음"
        kr_context = "아직 개장 전 사전 데이터가 충분하지 않습니다."
        
        if is_open:
            try:
                live_msg = ""
                try:
                    from datetime import datetime
                    f_list = self.bot.trader.get_kospi200_futures_list()
                    if f_list:
                        main_f = f_list[0].get('shcode')
                        f_px = get_price_data(self.bot.trader, main_f)
                        if f_px and f_px.get('price'): live_msg += f"- 코스피200 선물({main_f}): {f_px['price']}\n"
                    s_px = get_price_data(self.bot.trader, "005930")
                    if s_px and s_px.get('price'): live_msg += f"- 삼성전자(005930): {s_px['price']}\n"
                    if live_msg: live_msg = f"[장 출발 실시간 지표 - {datetime.now().strftime('%m-%d %H:%M')}]\n" + live_msg + "\n"
                except Exception: pass

                kr_summary = self.bot.public_data.get_market_summary()
                kr_context = live_msg + PublicDataClient.format_market_summary(kr_summary)
            except Exception as e:
                kr_context = f"한국 프리마켓 요약 실패: {e}"
                
        market_context = f"[미국 증시 동향]\n{us_context}\n\n[국내장 기초 데이터]\n{kr_context}"
        
        for chat_id_str, position in subs.items():
            try:
                title = "🌅 **[Unified Operations] 장전 포지션 시나리오 보고서 (v1.3.0)**" if is_open else "🌃 **[Unified Operations] 야간 장 마무리 분석 리포트 (v1.3.0)**"
                report_msg = (f"{title}\n\n📝 설정 포지션: `{position}`\n\nAI가 'Strategic Operations' 모드로 분석 중입니다. (1분 소요)")
                
                self.bot.send_message(chat_id_str, report_msg)
                reply = self.bot.advisor.get_portfolio_strategy(user_portfolio_text=position, market_context=market_context)
                self.bot.send_message(chat_id_str, reply)
            except Exception as e:
                print(f"Error sending scheduled report to {chat_id_str}: {e}")

    def run_schedule_loop(self):
        schedule.every().day.at("05:00").do(self.job_morning_report, is_open=False)
        schedule.every().day.at("08:50").do(self.job_morning_report, is_open=True)
        
        while True:
            schedule.run_pending()
            time.sleep(30)
