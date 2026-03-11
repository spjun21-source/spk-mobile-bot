import requests
import json
import time
import sys
import io
import os
import threading
import schedule
import atexit

# Windows: 콘솔/로그 cp949로 인한 이모지(❌ 등) UnicodeEncodeError 방지
# NOTE: Disabled - causes IO deadlock on Windows when running as background process
# if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
#     try:
#         sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
#         sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
#     except Exception:
#         pass
from src.clients.xing_rest import XingRestTrader
from src.clients.gemini import GeminiAdvisor
from src.clients.xing_realtime import XingRealtimeClient, parse_futures_execution, parse_futures_orderbook, TR_DESCRIPTIONS
from src.clients.public_data import PublicDataClient
from src.clients.brave_search import BraveSearchClient

from dotenv import load_dotenv

# --- Configuration ---
load_dotenv() # Load variables from .env file

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "REPLACE_ME")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "REPLACE_ME")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

# --- Global Instances (set in __main__) ---
trader = None            # XingRestTrader instance
realtime_client = None   # XingRealtimeClient instance
public_data = None       # PublicDataClient instance
brave_client = None      # BraveSearchClient instance
advisor = None           # GeminiAdvisor instance

# --- Subscriber Management ---
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")
SUBSCRIBERS_FILE = os.path.join(CONFIG_DIR, "subscribers.json")
TACTICAL_GUIDELINES_FILE = os.path.join(CONFIG_DIR, "tactical_guidelines.json")

def load_subscribers():
    if not os.path.exists(SUBSCRIBERS_FILE):
        return {}
    with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_subscribers(subs):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(subs, f, ensure_ascii=False, indent=4)

def monitor_guidelines():
    """
    Observer thread that polls tactical_guidelines.json for updates from Corebot.
    Uses a local state file to avoid re-processing the same directive on restarts.
    """
    last_processed_ts = ""
    state_file = os.path.join(CONFIG_DIR, "last_c2m_ts.txt")
    
    # Load last processed timestamp
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                last_processed_ts = f.read().strip()
        except Exception:
            pass

    while True:
        try:
            if os.path.exists(TACTICAL_GUIDELINES_FILE):
                mtime = os.path.getmtime(TACTICAL_GUIDELINES_FILE)
                # We still check mtime for efficiency, but use ts for correctness
                with open(TACTICAL_GUIDELINES_FILE, "r", encoding="utf-8") as f:
                    guidelines = json.load(f)
                
                current_ts = str(guidelines.get("timestamp", mtime))
                
                if current_ts != last_processed_ts:
                    last_processed_ts = current_ts
                    # Save state
                    with open(state_file, "w") as f:
                        f.write(current_ts)
                    
                    # Process guideline
                    code = guidelines.get("code") or guidelines.get("symbol")
                    target = guidelines.get("target") or guidelines.get("price")
                    condition = guidelines.get("condition", "<")
                    chat_id = guidelines.get("chat_id", "6532799784")

                    if condition == "<=": condition = "<"
                    if condition == ">=": condition = ">"
                    
                    if code and target:
                        try:
                            target_val = float(target)
                        except (ValueError, TypeError):
                            price_val = guidelines.get("price")
                            if price_val:
                                target_val = float(price_val)
                            else:
                                continue

                        # Add to active alerts
                        active_alerts.append({
                            'chat_id': int(chat_id),
                            'code': str(code),
                            'condition': condition,
                            'target': target_val
                        })
                        
                        msg = (
                            f"✅ **전략 하달 수신 완료 (C2M Bridge)**\n"
                            f"Target: `{code}` ({lookup_name(code)})\n"
                            f"Condition: {condition} {target_val}\n"
                            f"Status: **실시간 감시 기동됨**"
                        )
                        send_message(chat_id, msg)
                        print(f"[C2M] New guideline applied: {code} {condition} {target_val} (TS: {current_ts})")
                        
        except Exception as e:
            print(f"[C2M Error] monitor_guidelines: {e}")
        
        time.sleep(10)

# --- Futures Name Cache ---
futures_name_cache = {}  # code -> name mapping

def build_futures_cache(trader_instance):
    """Build a lookup cache of futures code -> name at startup."""
    global futures_name_cache
    try:
        codes = trader_instance.get_futures_code_list()
        for item in codes:
            shcode = item.get('shcode', '')
            hname = item.get('hname', '')
            if shcode and hname:
                futures_name_cache[shcode] = hname
        print(f"Futures cache built: {len(futures_name_cache)} items")
    except Exception as e:
        print(f"Warning: Could not build futures cache: {e}")

def lookup_name(code):
    """Look up the display name for a code."""
    # Check futures cache
    if code in futures_name_cache:
        return futures_name_cache[code]
    # Well-known stock codes
    stock_names = {
        '005930': '삼성전자',
        '000660': 'SK하이닉스',
        '035420': 'NAVER',
        '005380': '현대자동차',
        '051910': 'LG화학',
        '006400': '삼성SDI',
        '035720': '카카오',
        '003670': '포스코퓨처엠',
    }
    return stock_names.get(code, code)

# --- Operations ---
def send_message(chat_id, text, parse_mode="Markdown"):
    try:
        url = f"{TELEGRAM_API_URL}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
            
        res = requests.post(url, json=payload, timeout=15)
        data = res.json()
        
        if not data.get("ok"):
            print(f"⚠️ Telegram API Error: {data.get('description')}")
            # If Markdown parsing failed, try again without markdown
            if parse_mode is not None and "parse" in data.get("description", "").lower():
                print("🔄 Retrying without Markdown format...")
                send_message(chat_id, text, parse_mode=None)
                
    except Exception as e:
        print(f"[Error] sending message: {e}")

def get_price_data(code):
    """
    Helper to get price from Xing Trader.
    Detects stock codes vs futures codes and routes accordingly.
    Fallback to Underlying Stock if Future is 0 (Permission Issue).
    """
    # 0. Detect Stock Code (6-digit numeric like 005930)
    is_stock = code.isdigit() and len(code) == 6
    
    if is_stock:
        print(f"📊 Detected stock code: {code}")
        data = trader.get_stock_price(code)
        if data:
            return data
        return None
    
    # 1. Try Future
    data = trader.get_futures_price(code)
    
    # If valid future price, return it
    try:
        raw_price = str(data.get('price', '0')).replace(',', '').strip()
        price_val = float(raw_price)
    except:
        price_val = 0
        
    if data and price_val > 0:
        return data
        
    # 2. Fallback: Identify Underlying Stock
    # Simple mapping for Samsung Futures
    underlying_map = {
        "A1163000": "005930",
        "A1162000": "005930", 
        "101H6000": "005930",
        "A0163": "005930" # User provided code (KOSPI 200 Mar 26?) -> Proxy: Samsung
    }
    
    stock_code = underlying_map.get(code)
    if not stock_code and code.startswith("101"):
         stock_code = "005930" # Default to Samsung for KOSPI200 proxies for now
    
    if stock_code:
        print(f"⚠️ Future {code} blocked. Falling back to Stock {stock_code}...")
        s_data = trader.get_stock_price(stock_code)
        if s_data:
            s_data['_fallback_note'] = f"Derived from Stock {stock_code}"
            return s_data
            
    return data # Return original (empty/zero) if no fallback

# --- Global Alert Store ---
active_alerts = [] # Format: {'chat_id': id, 'code': code, 'condition': '>', 'price': 168000}

def check_alerts():
    """
    Background function to check active alerts.
    """
    while True:
        if active_alerts:
            # Group by code to minimize API calls
            codes_to_check = set(a['code'] for a in active_alerts)
            
            for code in codes_to_check:
                data = get_price_data(code)
                if not data: continue
                
                try:
                    raw_cprice = str(data.get('price', '0')).replace(',', '').strip()
                    current_price = float(raw_cprice)
                    if current_price == 0: continue
                except Exception as e:
                    print(f"Alert parsing error for {code} price {data.get('price')}: {e}")
                    continue

                # Check all alerts for this code
                for alert in active_alerts[:]: # Copy to allow removal
                    if alert['code'] == code:
                        triggered = False
                        if alert['condition'] == '>' and current_price > alert['target']:
                            triggered = True
                        elif alert['condition'] == '<' and current_price < alert['target']:
                            triggered = True
                            
                        if triggered:
                            msg = (
                                f"🚨 **SCENARIO TRIGGERED!**\n"
                                f"Asset: `{code}`\n"
                                f"Condition: Price {alert['condition']} {alert['target']}\n"
                                f"Current: **{current_price}**\n"
                                f"Action: **Check Chart / Execute Trade!**"
                            )
                            send_message(alert['chat_id'], msg)
                            active_alerts.remove(alert) # One-time alert
            
        time.sleep(5) # Check every 5 seconds

def handle_command(chat_id, text):
  try:
    parts = text.split()
    if not parts: return
    cmd = parts[0].lower()
    print(f"[CMD] {cmd} | text={text[:60]}", flush=True)
    
    print(f"Processing command: {cmd}")

    if cmd == "/subscribe":
        position = text.replace("/subscribe", "").strip()
        if not position:
            send_message(chat_id, "💡 사용법: `/subscribe [나의 포지션]`\n예시: `/subscribe 삼성전자 10주, 코스피200 선물 1개, 위클리 옵션 4계약(풋/콜) 매수·매도`\n매일 **05:00** 야간장 마감 분석, **08:50** 장전 포지션 시나리오 보고서를 자동 발송합니다.")
            return
            
        subs = load_subscribers()
        subs[str(chat_id)] = position
        save_subscribers(subs)
        send_message(chat_id, f"✅ **구독 완료!**\n저장된 포지션: `{position}`\n매일 05:00(야간장 마감), 08:50(장전 시나리오) 보고서를 보내드립니다.")
        return
        
    elif cmd == "/unsubscribe":
        subs = load_subscribers()
        if str(chat_id) in subs:
            del subs[str(chat_id)]
            save_subscribers(subs)
            send_message(chat_id, "[완료] **구독 취소 완료**\n더 이상 아침 리포트를 보내지 않습니다.")
        else:
            send_message(chat_id, "현재 구독 중이 아닙니다.")
        return

    elif cmd == "/id":
        send_message(chat_id, f"👤 **My Chat ID:** `{chat_id}`")
        return

    elif cmd in ["/start", "hello", "hi"]:
        msg = (
            "🤖 **SPK Mobile Bot v1.2.2 (Strategic Master)**\n"
            "Status: **Online**\n\n"
            "**Strategic Commands:**\n"
            "`/price [code]` - Check Price\n"
            "`/analyze [code]` - AI Strategy\n"
            "`/market` - 파생상품 종합 + AI분석 (v1.2.2)\n"
            "`/subscribe` - 장전/야간 전략 리포트 구독\n"
            "\n**Operations:**\n"
            "`/watch [code] [>|<] [price]` - Set Alert\n"
            "`/list` - List Futures\n"
            "`/id` - Get Chat ID"
        )
        send_message(chat_id, msg)

    elif cmd == "/watch":
        # Usage: /watch A1163000 > 168000
        if len(parts) < 4:
            send_message(chat_id, "Usage: `/watch [code] [>|<] [price]`\nEx: `/watch A1163000 > 168000`")
            return
            
        code = parts[1]
        condition = parts[2]
        try:
            target = float(parts[3])
        except:
             send_message(chat_id, "Price must be a number.")
             return
             
        if condition not in ['>', '<']:
             send_message(chat_id, "Condition must be `>` or `<`.")
             return

        active_alerts.append({
            'chat_id': chat_id,
            'code': code,
            'condition': condition,
            'target': target
        })
        send_message(chat_id, f"✅ **Alert Set**\nWill notify when `{code}` {condition} {target}")

    elif cmd == "/list":
        send_message(chat_id, "Fetching futures list...")
        codes = trader.get_futures_code_list()
        if not codes:
            send_message(chat_id, "No futures found.")
            return

        # Categorize
        index_futures = []
        samsung_futures = []
        other_futures = []
        for c in codes:
            shcode = c.get("shcode", "")
            hname = c.get("hname", "")
            if not shcode: continue
            entry = f"`{shcode}`: {hname}"
            if shcode.startswith("101"):
                index_futures.append(entry)
            elif '삼성전자' in hname:
                samsung_futures.append(entry)
            else:
                other_futures.append(entry)

        msg_parts = []
        if index_futures:
            msg_parts.append("📈 **KOSPI 200 Index:**\n" + "\n".join(index_futures[:5]))
        if samsung_futures:
            msg_parts.append("🏢 **삼성전자 (Samsung):**\n" + "\n".join(samsung_futures[:5]))
        if other_futures:
            msg_parts.append("📋 **Others (Top 10):**\n" + "\n".join(other_futures[:10]))

        msg = "\n\n".join(msg_parts)
        send_message(chat_id, f"**Futures List ({len(codes)} total)**\n\n{msg}")

    elif cmd == "/price":
        if len(parts) < 2:
            send_message(chat_id, "Usage: `/price [code]`")
            return
        code = parts[1].upper()
        data = get_price_data(code)
        
        if data:
            price = data.get('price', 0)
            name = lookup_name(code)
            fallback = data.get('_fallback_note', '')
            fallback_line = f"\n⚠️ _{fallback}_" if fallback else ""
            if price == 0:
                 send_message(chat_id, f"⚠️ **{name}** (`{code}`)\nPrice is 0 (Check Permissions)")
            else:
                 msg = (
                    f"📊 **{name}** (`{code}`)\n"
                    f"Price: **{price:,}**\n"
                    f"Open: {data.get('open', 'N/A'):,}\n"
                    f"High: {data.get('high', 'N/A'):,}\n"
                    f"Low: {data.get('low', 'N/A'):,}"
                    f"{fallback_line}"
                 )
                 send_message(chat_id, msg)
        else:
            send_message(chat_id, f"[오류] Could not fetch data for `{code}`")

    elif cmd == "/analyze":
        if len(parts) < 2:
            send_message(chat_id, "Usage: `/analyze [code]`")
            return
        code = parts[1]
        
        send_message(chat_id, f"🧠 **Gemini AI** is analyzing `{code}`...")
        
        # 1. Get Data (Xing realtime)
        data = get_price_data(code)
        if not data:
            send_message(chat_id, f"[오류] No market data found for {code}. Cannot analyze.")
            return
        
        # 2. Enrich with public data (전일 종가 context)
        try:
            if public_data:
                mkt = public_data.get_market_summary()
                futures_ctx = mkt.get('futures', [])
                calls_ctx = mkt.get('calls_top', [])[:3]
                puts_ctx = mkt.get('puts_top', [])[:3]
                ctx_lines = []
                if futures_ctx:
                    for f in futures_ctx[:2]:
                        ctx_lines.append(f"선물 {f.get('itmsNm','')}: 종가 {f.get('clpr',0)} (전일비 {f.get('vs',0)}) 거래량 {f.get('trqu',0)} 미결제 {f.get('opnint',0)}")
                if calls_ctx:
                    ctx_lines.append("콜옵션 Top: " + ", ".join(f"{c.get('itmsNm','').strip()} 종가{c.get('clpr',0)} 거래{c.get('trqu',0)}" for c in calls_ctx))
                if puts_ctx:
                    ctx_lines.append("풋옵션 Top: " + ", ".join(f"{p.get('itmsNm','').strip()} 종가{p.get('clpr',0)} 거래{p.get('trqu',0)}" for p in puts_ctx))
                if ctx_lines:
                    data['_derivatives_context'] = "\n".join(ctx_lines)
        except Exception as e:
            print(f"Enrich error (non-fatal): {e}")
            
        # 3. Ask Gemini
        analysis = advisor.get_analysis(data, symbol=code)
        
        # 4. Send
        send_message(chat_id, f"🤖 **Strategy Scenario**\n\n{analysis}")

    elif cmd in ["/buy", "/sell"]:
        # Usage: /buy A1163000 1 168000
        if len(parts) < 4:
            send_message(chat_id, f"Usage: `{cmd} [code] [qty] [price]`")
            return
        
        code = parts[1]
        qty = parts[2]
        price = parts[3]
        # 2=Buy, 1=Sell in Xing API
        type_code = "2" if cmd == "/buy" else "1" 
        
        if not qty.isdigit():
             send_message(chat_id, "Quantity must be a number.")
             return

        send_message(chat_id, f"⏳ Sending Order: {cmd.upper()} {qty} of {code} @ {price}...")
        
        # Execute
        result = trader.place_futures_order(code, qty, price, type_code)
        
        if result and "CFOAT00100OutBlock1" in result:
             ord_no = result["CFOAT00100OutBlock1"]["OrdNo"]
             send_message(chat_id, f"✅ **Order Placed!**\nNumber: `{ord_no}`\n{cmd.upper()} {qty} of {code} at {price}")
        elif result and "rsp_msg" in result:
             send_message(chat_id, f"[오류] Order Failed: {result['rsp_msg']}")
        else:
             send_message(chat_id, f"[오류] Order Failed (Unknown Error): {result}")

    elif cmd == "/realtime":
        if len(parts) < 2:
            send_message(chat_id, "Usage: `/realtime [code]`\nEx: `/realtime 101V6000`")
            return
        code = parts[1].upper()
        duration = int(parts[2]) if len(parts) > 2 else 10
        duration = min(duration, 30)  # Cap at 30s

        if not realtime_client or not realtime_client.is_connected():
            send_message(chat_id, "⚠️ Realtime WebSocket not connected. Use `/rt_status` to check.")
            return

        send_message(chat_id, f"📡 **Live Feed** `{code}` for {duration}s...")
        collected = []

        def on_exec(tr_cd, tr_key, body):
            d = parse_futures_execution(body)
            collected.append(d)

        realtime_client.on_callback("FC0", on_exec)
        realtime_client.subscribe("FC0", code)
        time.sleep(duration)
        realtime_client.unsubscribe("FC0", code)

        # Remove callback
        if "FC0" in realtime_client._callbacks:
            try: realtime_client._callbacks["FC0"].remove(on_exec)
            except: pass

        if collected:
            lines = []
            for d in collected[-15:]:  # Last 15 entries
                bs = "🔴" if d.get('buysell') == '1' else "🔵" if d.get('buysell') == '2' else "⚪"
                lines.append(f"{bs} {d.get('time','')} | {d.get('price',''):>10} | Δ{d.get('change','')} | Vol:{d.get('volume','')}")
            msg = f"📊 **{code} Execution Feed** ({len(collected)} ticks)\n```\n" + "\n".join(lines) + "\n```"
            send_message(chat_id, msg)
        else:
            send_message(chat_id, f"⚠️ No data received for `{code}` in {duration}s.\n(Market may be closed: 09:00-15:45 KST)")

    elif cmd == "/orderbook":
        if len(parts) < 2:
            send_message(chat_id, "Usage: `/orderbook [code]`\nEx: `/orderbook 101V6000`")
            return
        code = parts[1].upper()

        if not realtime_client or not realtime_client.is_connected():
            send_message(chat_id, "⚠️ Realtime WebSocket not connected.")
            return

        send_message(chat_id, f"📋 Fetching orderbook for `{code}`...")
        orderbook = [None]

        def on_ob(tr_cd, tr_key, body):
            orderbook[0] = parse_futures_orderbook(body)

        realtime_client.on_callback("FH0", on_ob)
        realtime_client.subscribe("FH0", code)
        time.sleep(3)  # Wait for first orderbook snapshot
        realtime_client.unsubscribe("FH0", code)

        if "FH0" in realtime_client._callbacks:
            try: realtime_client._callbacks["FH0"].remove(on_ob)
            except: pass

        if orderbook[0]:
            ob = orderbook[0]
            lines = ["  매도(Ask)     수량  │  매수(Bid)     수량"]
            lines.append("  ───────────  ─────  │  ───────────  ─────")
            for i in range(5, 0, -1):
                ask = ob.get(f'ask{i}', '-')
                aq = ob.get(f'ask{i}_qty', '-')
                bid = ob.get(f'bid{i}', '-')
                bq = ob.get(f'bid{i}_qty', '-')
                lines.append(f"  {ask:>10}  {aq:>5}  │  {bid:>10}  {bq:>5}")
            msg = f"📋 **{code} Orderbook**\n```\n" + "\n".join(lines) + "\n```"
            send_message(chat_id, msg)
        else:
            send_message(chat_id, f"⚠️ No orderbook data for `{code}`.\n(Market may be closed)")

    elif cmd == "/futures":
        bas_dt = parts[1] if len(parts) > 1 else None
        send_message(chat_id, "📈 선물 시세 조회 중...")
        try:
            data = public_data.get_kospi200_futures(bas_dt)
            msg = PublicDataClient.format_futures_table(data)
            send_message(chat_id, msg)
        except Exception as e:
            send_message(chat_id, f"[오류] 선물 시세 조회 실패: {e}")

    elif cmd == "/options":
        bas_dt = parts[1] if len(parts) > 1 else None
        send_message(chat_id, "📊 옵션 시세 조회 중...")
        try:
            data = public_data.get_kospi200_options(bas_dt)
            msg = PublicDataClient.format_options_table(data)
            send_message(chat_id, msg)
        except Exception as e:
            send_message(chat_id, f"[오류] 옵션 시세 조회 실패: {e}")

    elif cmd == "/market":
        send_message(chat_id, "🏦 시장 종합 분석 중... (공공데이터 + AI)")
        try:
            summary = public_data.get_market_summary()
            summary_msg = PublicDataClient.format_market_summary(summary)
            send_message(chat_id, summary_msg)

            # AI commentary on the market data
            futures_data = summary.get('futures', [])
            if futures_data and advisor:
                # Get Live Proxy
                live_context = ""
                try:
                    from datetime import datetime
                    live_f_px = 0
                    live_msg = f"\n[실시간 시장 지표 - {datetime.now().strftime('%m-%d %H:%M')}]\n"
                    
                    f_list = trader.get_kospi200_futures_list()
                    if f_list:
                        main_f_code = f_list[0].get('shcode')
                        f_px = get_price_data(main_f_code)
                        if f_px and f_px.get('price'):
                            live_f_px = float(f_px['price'])
                            live_msg += f"- 코스피200 선물({main_f_code}): {f_px['price']}\n"
                    
                    s_px = get_price_data("005930")
                    if s_px and s_px.get('price'):
                        live_msg += f"- 삼성전자(005930): {s_px['price']}\n"
                except Exception as e:
                    live_msg = ""
                    print(f"Market proxy fetch error: {e}")

                main_f = futures_data[0]
                ai_ctx = {
                    'price': live_f_px if live_f_px > 0 else float(main_f.get('clpr', 0)),
                    'open': float(main_f.get('mkp', 0)),
                    'high': float(main_f.get('hipr', 0)),
                    'low': float(main_f.get('lopr', 0)),
                    '_derivatives_context': live_msg + "\n" + summary_msg if live_msg else summary_msg
                }
                analysis = advisor.get_analysis(ai_ctx, symbol="코스피200 선물")
                send_message(chat_id, f"🤖 **AI 시장 분석**\n\n{analysis}")
        except Exception as e:
            send_message(chat_id, f"[오류] 시장 종합 조회 실패: {e}")

    elif cmd == "/rt_status":
        if realtime_client:
            connected = realtime_client.is_connected()
            subs = list(realtime_client._subscriptions.keys())
            status_icon = "🟢" if connected else "🔴"
            msg = (
                f"{status_icon} **Realtime WebSocket**\n"
                f"Connected: **{connected}**\n"
                f"Server: `{realtime_client.ws_url}`\n"
                f"Active Subscriptions: {len(subs)}\n"
            )
            if subs:
                for tr_cd, tr_key in subs:
                    desc = TR_DESCRIPTIONS.get(tr_cd, tr_cd)
                    msg += f"  • `{tr_cd}` ({desc}) / `{tr_key}`\n"
            send_message(chat_id, msg)
        else:
            send_message(chat_id, "🔴 Realtime client not initialized.")

    else:
        # Natural Language Handling (Conversational Intent Routing)
        send_message(chat_id, "🧠 분석 중입니다. (30초~1분 소요, 잠시만 기다려 주세요.)")
        
        try:
            # 1. Analyze Intent
            intent_json = advisor.analyze_intent(text)
            
            # API가 에러/안내 문자열을 반환한 경우 그대로 전달 (JSON 파싱하지 않음)
            if intent_json.startswith("⚠️") or intent_json.startswith("[오류]") or intent_json.startswith("[안내]"):
                send_message(chat_id, intent_json)
                return
                
            intent = json.loads(intent_json)
            
            action = intent.get("action", "chat")
            target_code = intent.get("target_code", "")
            
            print(f"Parsed Intent: Action={action}, Code={target_code}")
            
            # 2. Route Action
            if action == "price":
                if target_code:
                    data = get_price_data(target_code)
                    if data:
                        name = lookup_name(target_code)
                        data['asset_name'] = name # Inject for Gemini to use
                        reply = advisor.format_response(text, data, data_type="price")
                    else:
                        reply = f"[오류] `{target_code}`에 대한 가격 데이터를 찾을 수 없어요."
                else:
                    reply = "어떤 종목의 가격을 원하시는지 말씀해 주세요! (예: 삼성전자 가격 알려줘)"
            
            elif action == "stock_analysis":
                if target_code:
                    name = lookup_name(target_code)
                    send_message(chat_id, f"📊 **{name}**(`{target_code}`) 최근 동향 및 추세 분석 중입니다...\n(인터넷 뉴스 검색 및 캔들 데이터 수집이 포함되어 잠시 소요됩니다.)")
                    
                    price_data = get_price_data(target_code)
                    if not price_data:
                        price_data = {"error": f"No real-time data for {name}"}
                    
                    # --- Multi-Timeframe Candle Data (Supply-Demand Analysis) ---
                    daily_data = []
                    min5_data = []
                    min15_data = []
                    
                    # Case 1: Samsung Electronics (Stock or Future Proxy)
                    if target_code == "005930" or target_code.startswith("101"):
                        stock_code = "005930"
                        print(f"Fetching multi-timeframe candles for {stock_code}...", flush=True)
                        daily_data = trader.get_stock_chart_daily(stock_code, count=10)
                        min5_data = trader.get_stock_chart_minute(stock_code, interval=5, count=10)
                        min15_data = trader.get_stock_chart_minute(stock_code, interval=15, count=10)
                    
                    search_query = f"{name} 주식 주가 시세 장기 전망 분석"
                    search_results = brave_client.search(search_query) if brave_client else "인터넷 검색 모듈 비활성화"
                    
                    # ByPASS ready context construction
                    candle_context = {
                        "daily": daily_data if daily_data else "No daily data",
                        "min5": min5_data if min5_data else "No 5min data",
                        "min15": min15_data if min15_data else "No 15min data"
                    }
                    
                    # Always call the enhanced multi-timeframe response (ByPASS aware)
                    reply = advisor.format_multi_timeframe_response(
                        text, f"{name}({target_code})", daily_data, min5_data, min15_data, price_data, search_results
                    )
                else:
                    reply = "어떤 종목을 분석해 드릴까요? (예: 지난 주 삼성전자 주가 분석해줘)"
            
            elif action == "night_market":
                # Direct formatting — no Gemini API call needed, saves quota
                try:
                    summary = public_data.get_market_summary()
                    futures_list = summary.get('futures', [])
                    if futures_list:
                        lines = []
                        for f in futures_list[:3]:
                            name = f.get('itmsNm', '?')
                            clpr = f.get('clpr', '0')
                            vs = f.get('vs', '0')
                            mkp = f.get('mkp', '0')
                            hipr = f.get('hipr', '0')
                            lopr = f.get('lopr', '0')
                            trqu = f.get('trqu', '0')
                            try:
                                vs_val = float(vs)
                                arrow = "+" if vs_val >= 0 else ""
                            except:
                                arrow = ""
                            lines.append(
                                f"*{name}*\n"
                                f"  종가: *{clpr}* ({arrow}{vs})\n"
                                f"  시가: {mkp} / 고가: {hipr} / 저가: {lopr}\n"
                                f"  거래량: {int(trqu):,}\n"
                            )
                        calls = summary.get('calls_top', [])
                        puts = summary.get('puts_top', [])
                        if calls or puts:
                            lines.append("\n*주요 옵션*")
                            for c in calls[:2]:
                                lines.append(f"  콜 {c.get('itmsNm','?')}: {c.get('clpr','?')} ({c.get('vs','?')})")
                            for p in puts[:2]:
                                lines.append(f"  풋 {p.get('itmsNm','?')}: {p.get('clpr','?')} ({p.get('vs','?')})")
                        bas_dt_str = futures_list[0].get('basDt', '')
                        date_display = f"{bas_dt_str[:4]}-{bas_dt_str[4:6]}-{bas_dt_str[6:]}" if len(bas_dt_str) == 8 else bas_dt_str
                        reply = (
                            f"야간 선물/옵션 시황 리포트\n"
                            f"(기준일: {date_display}, 조회: {time.strftime('%H:%M')})\n\n"
                            + "\n".join(lines)
                        )
                    else:
                        reply = "야간 선물 데이터를 가져올 수 없습니다."
                except Exception as night_e:
                    reply = f"야간 시황 조회 실패: {night_e}"

            # Action 'market' has been merged with 'portfolio_strategy' for Bypass support
            elif action == "futures":
                data = public_data.get_kospi200_futures()
                reply = advisor.format_response(text, data, data_type="futures list")
                
            elif action == "options":
                data = public_data.get_kospi200_options()
                reply = advisor.format_response(text, data, data_type="options list")
                
            elif action == "web_search":
                if target_code:
                    send_message(chat_id, f"🌐 인터넷 검색 중: `{target_code}`...")
                    search_results = brave_client.search(target_code)
                    reply = advisor.format_response(text, search_results, data_type="web search results")
                else:
                    reply = "무엇을 검색해 드릴까요? (예: 미국 나스닥 상황 알려줘)"

            elif action in ["portfolio_strategy", "market"]:
                msg_text = "📊 보유 포지션 기반 시나리오 분석 중..." if action == "portfolio_strategy" else "📊 실시간 장중 시황 및 전략 시나리오 분석 중..."
                send_message(chat_id, f"{msg_text}\n(데이터 수집·AI 분석에 10초~30초 소요, 잠시만 기다려 주세요.)")
                print(f"DEBUG: {action} started.")
                
                # 1. Fetch pre-market context (US wrap-up & KOSPI summary)
                print("DEBUG: Trying Brave search...")
                us_market_context = brave_client.search("간밤 미국 증시 마감 요약 주요 지수 특징주") if brave_client else "미국 증시 검색 불가"
                print("DEBUG: Brave search finished.")
                
                # 2. Extract Tickers and Fetch Real-time Prices
                # Look for 6-digit stock codes (e.g., 005930) or futures codes
                import re
                tickers = re.findall(r"\b\d{6}\b", text)
                realtime_prices = {}
                for t in tickers:
                    px_data = get_price_data(t)
                    if px_data and px_data.get('price'):
                         realtime_prices[t] = px_data['price']
                         
                # 2.5 Inject Live Proxies if missing
                print("DEBUG: Trying live proxy fetch...")
                try:
                    from datetime import datetime
                    if "005930" not in realtime_prices:
                        print("DEBUG: Fetching 005930...")
                        s_px = get_price_data("005930")
                        if s_px and s_px.get('price'): realtime_prices["005930"] = s_px['price']
                    
                    # Try KOSPI200 Futures
                    print("DEBUG: Fetching KOSPI 200 list...")
                    f_list = trader.get_kospi200_futures_list()
                    if f_list:
                        main_f = f_list[0].get('shcode')
                        if main_f and main_f not in realtime_prices:
                            print(f"DEBUG: Fetching main future {main_f}...")
                            f_px = get_price_data(main_f)
                            if f_px and f_px.get('price'): realtime_prices[main_f] = f_px['price']
                    print("DEBUG: Live proxy fetch finished.")
                except Exception as e:
                    print(f"Proxy fetch error: {e}")
                
                price_context = ""
                if realtime_prices:
                    from datetime import datetime
                    curr_time = datetime.now().strftime('%m-%d %H:%M')
                    price_context = f"\n[현재 시간({curr_time}) 기준 실시간 지표]\n" + "\n".join([f"- {lookup_name(k)} ({k}): {v:,}원" for k,v in realtime_prices.items()])

                try:
                    print("DEBUG: Trying public data get_market_summary...")
                    kr_summary = public_data.get_market_summary()
                    kr_market_context = PublicDataClient.format_market_summary(kr_summary)
                    print("DEBUG: Public data finish...")
                except Exception as e:
                    kr_market_context = f"한국 시장 요약 가져오기 실패: {e}"
                
                # Format contexts into a single string for Gemini
                market_context = f"{price_context}\n\n[미국 증시 동향]\n{us_market_context}\n\n[국내 파생/현물 기초 데이터]\n{kr_market_context}"
                
                # 3. Call Gemini for strategy 
                # If market_context has missing parts (e.g., night session futures), 
                # Gemini v1.2.2 is now instructed to provide a ByPASS/Macro report instead of failing.
                print("DEBUG: Trying Gemini get_portfolio_strategy...")
                portfolio_input = text if action == "portfolio_strategy" else "단순 시황 요약 요청이므로 특정 포지션은 없음."
                reply = advisor.get_portfolio_strategy(user_portfolio_text=portfolio_input, market_context=market_context)
                print("DEBUG: Gemini get_portfolio_strategy finish.")
                
            elif action == "weekly_strategy":
                send_message(chat_id, "📊 주말 글로벌/국내 시황 및 다음 주 KOSPI200/위클리 옵션 전략을 분석 중입니다...\n(데이터 수집·AI 분석에 약 1분 소요됩니다.)")
                
                # 1. Fetch US weekend wrap-up
                us_market_context = brave_client.search("미국 나스닥 증시 주간 마감 요약 KOSPI 주간 전망") if brave_client else "미국 증시 검색 불가"
                
                # 2. Fetch KR current snapshot
                try:
                    kr_summary = public_data.get_market_summary()
                    kr_market_context = PublicDataClient.format_market_summary(kr_summary)
                except Exception as e:
                    kr_market_context = f"한국 시장 요약 데이터 실패: {e}"

                market_context = f"[미국 및 글로벌 증시 주간 동향]\n{us_market_context}\n\n[국내 KOSPI200/옵션 기초 상황]\n{kr_market_context}"
                
                # 3. Request portfolio strategy using the pre-defined target scenario
                scenario_prompt = "KOSPI200 선물 1계약 양방향 타점, 위클리 옵션 콜 2계약 및 풋 2계약 (양매수/양매도) 대응 전략"
                reply = advisor.get_portfolio_strategy(user_portfolio_text=scenario_prompt, market_context=market_context)
                
            else: # chat or unknown
                market_data = None
                if target_code:
                     market_data = get_price_data(target_code)
                reply = advisor.get_chat_response(text, market_data, symbol=target_code if target_code else "General")
            
            # 3. Send final conversational reply
            send_message(chat_id, reply)
            
        except json.JSONDecodeError:
            print(f"Failed to parse intent JSON: {intent_json}")
            safe_msg = intent_json.replace("\u274c", "[X]")
            send_message(chat_id, f"[오류] AI 서버 응답 오류:\n{safe_msg}")
        except Exception as e:
            import traceback
            print(f"Intent routing error: {e}", flush=True)
            traceback.print_exc()
            sys.stdout.flush()
            send_message(chat_id, f"[오류] {e}")

  except Exception as e:
    import traceback
    print(f"CRITICAL ERROR in handle_command: {e}", flush=True)
    traceback.print_exc()
    sys.stdout.flush()
    try:
        send_message(chat_id, f"치명적 오류: {e}")
    except:
        pass

def run_bot():
    offset = 0
    # 토큰 설정 확인 (데스크탑에서 .env 누락 시 바로 확인 가능)
    token_ok = TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN.strip() != "" and TELEGRAM_BOT_TOKEN != "REPLACE_ME"
    if not token_ok:
        print("ERROR: TELEGRAM_BOT_TOKEN not set. Add TELEGRAM_BOT_TOKEN=... to .env in project root.")
        print("Bot will not receive messages until .env is configured.")
    else:
        try:
            r = requests.get(f"{TELEGRAM_API_URL}/getMe", timeout=10)
            info = r.json()
            if info.get("ok"):
                print(f"Telegram bot connected: @{info['result'].get('username', '?')}")
            else:
                print(f"Telegram token invalid: {info}")
        except Exception as e:
            print(f"Telegram connection check failed: {e}")
    print("Bot polling started...")
    
    while True:
        try:
            payload = {
                "offset": offset,
                "timeout": 30,
                "allowed_updates": ["message"]
            }
            response = requests.post(f"{TELEGRAM_API_URL}/getUpdates", json=payload, timeout=40)
            data = response.json()
            
            if data.get("ok"):
                for update in data.get("result", []):
                    update_id = update["update_id"]
                    if update_id >= offset:
                        offset = update_id + 1
                    
                    if "message" in update and "text" in update["message"]:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"]["text"]
                        user = update["message"]["from"].get("username", "Unknown")
                        
                        print(f"[Msg] {user}: {text}")
                        # Process command
                        threading.Thread(target=handle_command, args=(chat_id, text)).start()
                        
            else:
                print(f"API Error: {data}")
                time.sleep(5)
                
        except Exception as e:
            print(f"Polling Error: {e}")
            time.sleep(5)

# --- Scheduler ---
def job_morning_report(is_open=False):
    print(f"⏰ Running Scheduled Report (is_open={is_open})...")
    subs = load_subscribers()
    if not subs: 
        print("No subscribers found.")
        return
    
    # 1. Fetch Market Context
    us_context = brave_client.search("간밤 미국 증시 마감 요약 주요 지수 특징주") if brave_client else "미국 증시 정보 없음"
    
    kr_context = "아직 개장 전 사전 데이터가 충분하지 않습니다."
    if is_open:
        try:
            live_msg = ""
            try:
                from datetime import datetime
                f_list = trader.get_kospi200_futures_list()
                if f_list:
                    main_f = f_list[0].get('shcode')
                    f_px = get_price_data(main_f)
                    if f_px and f_px.get('price'): live_msg += f"- 코스피200 선물({main_f}): {f_px['price']}\n"
                s_px = get_price_data("005930")
                if s_px and s_px.get('price'): live_msg += f"- 삼성전자(005930): {s_px['price']}\n"
                if live_msg: live_msg = f"[장 출발 실시간 지표 - {datetime.now().strftime('%m-%d %H:%M')}]\n" + live_msg + "\n"
            except Exception as e:
                print(f"Morning report proxy fetch error: {e}")

            kr_summary = public_data.get_market_summary()
            kr_context = live_msg + PublicDataClient.format_market_summary(kr_summary)
        except Exception as e:
            kr_context = f"한국 프리마켓 요약 실패: {e}"
            
    market_context = f"[미국 증시 동향]\n{us_context}\n\n[국내장 기초 데이터]\n{kr_context}"
    
    # 2. Iterate and send
    for chat_id_str, position in subs.items():
        try:
            chat_id = int(chat_id_str)
            title = "🌅 **[Strategic Master] 장전 포지션 시나리오 보고서 (v1.2.2)**" if is_open else "🌃 **[Strategic Master] 야간 장 마무리 분석 리포트 (v1.2.2)**"
            send_message(chat_id, f"{title}\n\n📝 설정 포지션: `{position}`\n\nAI가 'Strategic Operations' 모드로 분석 중입니다. (1분 소요)")
            
            reply = advisor.get_portfolio_strategy(user_portfolio_text=position, market_context=market_context)
            send_message(chat_id, reply)
        except Exception as e:
            print(f"Error sending scheduled report to {chat_id_str}: {e}")

def run_schedule():
    # KST 기준: 05:00 야간장 마감, 08:50 장전 시나리오
    schedule.every().day.at("05:00").do(job_morning_report, is_open=False)
    schedule.every().day.at("08:50").do(job_morning_report, is_open=True)
    
    while True:
        schedule.run_pending()
        time.sleep(30)

# --- Main Entry ---
if __name__ == "__main__":
    # PID file for scripts\start_bot.bat / stop_bot.bat / status_bot.bat
    _root = os.path.join(os.path.dirname(__file__), "..")
    _pid_file = os.path.abspath(os.path.join(_root, "spk_bot.pid"))
    try:
        with open(_pid_file, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    def _remove_pid():
        try:
            if os.path.exists(_pid_file):
                os.remove(_pid_file)
        except Exception:
            pass
    atexit.register(_remove_pid)

    # Initialize Global Instances
    print("Initializing Xing API...", flush=True)
    trader = XingRestTrader()
    if not trader.get_access_token():
        print("Warning: Xing Token Failed. Bot will start but API calls may fail.", flush=True)
    else:
        print("Xing API Token obtained successfully.", flush=True)

    print("Building futures cache...", flush=True)
    build_futures_cache(trader)

    print("Initializing Public Data Client...", flush=True)
    public_data = PublicDataClient()

    print("Initializing Brave Search Client...", flush=True)
    brave_client = BraveSearchClient(api_key=BRAVE_API_KEY)

    print("Initializing Gemini Advisor...", flush=True)
    advisor = GeminiAdvisor(GEMINI_API_KEY)
    
    # Initialize Realtime WebSocket Client
    print("Initializing Realtime WebSocket...", flush=True)
    realtime_client = XingRealtimeClient()
    if realtime_client.start():
        print("Realtime WebSocket connected.", flush=True)
    else:
        print("Warning: Realtime WebSocket failed. /realtime commands may not work.", flush=True)

    # Start Alert Thread
    print("Starting Alert Monitor...")
    threading.Thread(target=check_alerts, daemon=True).start()
    
    # Start Scheduler Thread
    print("Starting Automated Reporting Scheduler...")
    threading.Thread(target=run_schedule, daemon=True).start()
    
    # Start C2M Guideline Observer Thread
    print("Starting C2M Command Bridge Observer...")
    threading.Thread(target=monitor_guidelines, daemon=True).start()
    
    run_bot()
