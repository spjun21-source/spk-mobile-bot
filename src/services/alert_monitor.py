import os
import json
import time
import schedule
from src.utils.helpers import lookup_name, get_price_data

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "config")
SUBSCRIBERS_FILE = os.path.join(CONFIG_DIR, "subscribers.json")
TACTICAL_GUIDELINES_FILE = os.path.join(CONFIG_DIR, "tactical_guidelines.json")
ALERTS_FILE = os.path.join(CONFIG_DIR, "alerts_db.json")

class AlertMonitor:
    def __init__(self, bot_context):
        self.bot = bot_context
        self.active_alerts = []
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self.load_alerts()

    def load_alerts(self):
        try:
            if os.path.exists(ALERTS_FILE):
                with open(ALERTS_FILE, 'r') as f:
                    self.active_alerts = json.load(f)
                print(f"Loaded {len(self.active_alerts)} active alerts from DB.")
        except Exception as e:
            print(f"Failed to load alerts: {e}")
            self.active_alerts = []

    def save_alerts(self):
        try:
            with open(ALERTS_FILE, 'w') as f:
                json.dump(self.active_alerts, f)
        except Exception as e:
            print(f"Failed to save alerts: {e}")

    def add_alert(self, chat_id, code, condition, target):
        self.active_alerts.append({
            'chat_id': chat_id,
            'code': code,
            'condition': condition,
            'target': target
        })
        self.save_alerts()

    def check_alerts_loop(self):
        """Background function to check active alerts."""
        while True:
            if self.active_alerts:
                codes_to_check = set(a['code'] for a in self.active_alerts)
                for code in codes_to_check:
                    data = get_price_data(self.bot.trader, code)
                    if not data: continue
                    
                    try:
                        raw_cprice = str(data.get('price', '0')).replace(',', '').strip()
                        current_price = float(raw_cprice)
                        if current_price == 0: continue
                    except Exception as e:
                        continue

                    for alert in self.active_alerts[:]: 
                        if alert['code'] == code:
                            triggered = False
                            if alert['condition'] == '>' and current_price > alert['target']: triggered = True
                            elif alert['condition'] == '<' and current_price < alert['target']: triggered = True
                            
                            if triggered:
                                msg = (
                                    f"🚨 **SCENARIO TRIGGERED!**\n"
                                    f"Asset: `{code}`\n"
                                    f"Condition: Price {alert['condition']} {alert['target']}\n"
                                    f"Current: **{current_price}**\n"
                                    f"Action: **Check Chart / Execute Trade!**"
                                )
                                self.bot.send_message(alert['chat_id'], msg)
                                self.active_alerts.remove(alert)
                                self.save_alerts()
            time.sleep(5)

    def monitor_guidelines_loop(self):
        """Observer thread that polls tactical_guidelines.json for updates from Corebot."""
        last_processed_ts = ""
        state_file = os.path.join(CONFIG_DIR, "last_c2m_ts.txt")
        
        if os.path.exists(state_file):
            try:
                with open(state_file, "r") as f:
                    last_processed_ts = f.read().strip()
            except Exception: pass

        while True:
            try:
                if os.path.exists(TACTICAL_GUIDELINES_FILE):
                    mtime = os.path.getmtime(TACTICAL_GUIDELINES_FILE)
                    with open(TACTICAL_GUIDELINES_FILE, "r", encoding="utf-8") as f:
                        guidelines = json.load(f)
                    
                    current_ts = str(guidelines.get("timestamp", mtime))
                    if current_ts != last_processed_ts:
                        last_processed_ts = current_ts
                        with open(state_file, "w") as f: f.write(current_ts)
                        
                        code = guidelines.get("code") or guidelines.get("symbol")
                        target = guidelines.get("target") or guidelines.get("price")
                        condition = guidelines.get("condition", "<")
                        chat_id = guidelines.get("chat_id", "6532799784")

                        if condition == "<=": condition = "<"
                        if condition == ">=": condition = ">"
                        
                        if code and target:
                            try: target_val = float(target)
                            except (ValueError, TypeError):
                                price_val = guidelines.get("price")
                                if price_val: target_val = float(price_val)
                                else: continue

                            self.add_alert(int(chat_id), str(code), condition, target_val)
                            
                            msg = (f"✅ **전략 하달 수신 완료 (C2M Bridge)**\nTarget: `{code}` ({lookup_name(code)})\nCondition: {condition} {target_val}\nStatus: **실시간 감시 기동됨**")
                            self.bot.send_message(chat_id, msg)
                            
                            try:
                                report_file = os.path.join(CONFIG_DIR, "execution_report.json")
                                report_data = {"timestamp": current_ts, "status": "RECEIVED_AND_MONITORING", "code": code, "target": target_val, "condition": condition}
                                with open(report_file, "w", encoding="utf-8") as rf:
                                    json.dump(report_data, rf, ensure_ascii=False, indent=2)
                            except Exception: pass
            except Exception: pass
            time.sleep(10)
