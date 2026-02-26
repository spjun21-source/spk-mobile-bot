
import requests
import json
import time
import sys
import threading
from src.clients.xing_rest import XingRestTrader
from src.clients.gemini import GeminiAdvisor
from src.clients.xing_realtime import XingRealtimeClient, parse_futures_execution, parse_futures_orderbook, TR_DESCRIPTIONS
from src.clients.public_data import PublicDataClient

# --- Configuration ---
TELEGRAM_BOT_TOKEN = "8495846438:AAGnfhzjLg9wTmxNkqBesQukMhEfwxZXjb0"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GEMINI_API_KEY = "AIzaSyDxqhHTnMuEhtNppo9aDtj8vg0GOzoO6hQ"

# --- Global Instances (set in __main__) ---
realtime_client = None  # XingRealtimeClient instance
public_data = None       # PublicDataClient instance

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
def send_message(chat_id, text):
    try:
        url = f"{TELEGRAM_API_URL}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

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
        price_val = float(data.get('price', 0))
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
                    current_price = float(data.get('price', 0))
                    if current_price == 0: continue
                except:
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
    parts = text.split()
    if not parts: return
    cmd = parts[0].lower()
    
    print(f"Processing command: {cmd}")

    if cmd in ["/start", "hello", "hi"]:
        msg = (
            "🤖 **SPK Mobile Bot (Gemini AI)**\n"
            "Status: **Online**\n\n"
            "**Commands:**\n"
            "`/price [code]` - Check Price\n"
            "`/analyze [code]` - AI Strategy\n"
            "`/watch [code] [>|<] [price]` - Set Alert\n"
            "`/list` - List Futures\n"
            "`/futures [date]` - 선물 시세 (공공데이터)\n"
            "`/options [date]` - 옵션 시세 (공공데이터)\n"
            "`/market` - 파생상품 종합 + AI분석\n"
            "`/realtime [code]` - Live Execution Feed\n"
            "`/orderbook [code]` - Live Orderbook\n"
            "`/rt_status` - Realtime Status"
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
            send_message(chat_id, f"❌ Could not fetch data for `{code}`")

    elif cmd == "/analyze":
        if len(parts) < 2:
            send_message(chat_id, "Usage: `/analyze [code]`")
            return
        code = parts[1]
        
        send_message(chat_id, f"🧠 **Gemini AI** is analyzing `{code}`...")
        
        # 1. Get Data (Xing realtime)
        data = get_price_data(code)
        if not data:
            send_message(chat_id, f"❌ No market data found for {code}. Cannot analyze.")
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
             send_message(chat_id, f"❌ Order Failed: {result['rsp_msg']}")
        else:
             send_message(chat_id, f"❌ Order Failed (Unknown Error): {result}")

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
            send_message(chat_id, f"❌ 선물 시세 조회 실패: {e}")

    elif cmd == "/options":
        bas_dt = parts[1] if len(parts) > 1 else None
        send_message(chat_id, "📊 옵션 시세 조회 중...")
        try:
            data = public_data.get_kospi200_options(bas_dt)
            msg = PublicDataClient.format_options_table(data)
            send_message(chat_id, msg)
        except Exception as e:
            send_message(chat_id, f"❌ 옵션 시세 조회 실패: {e}")

    elif cmd == "/market":
        send_message(chat_id, "🏦 시장 종합 분석 중... (공공데이터 + AI)")
        try:
            summary = public_data.get_market_summary()
            summary_msg = PublicDataClient.format_market_summary(summary)
            send_message(chat_id, summary_msg)

            # AI commentary on the market data
            futures_data = summary.get('futures', [])
            if futures_data and advisor:
                main_f = futures_data[0]
                ai_ctx = {
                    'price': float(main_f.get('clpr', 0)),
                    'open': float(main_f.get('mkp', 0)),
                    'high': float(main_f.get('hipr', 0)),
                    'low': float(main_f.get('lopr', 0)),
                    '_derivatives_context': summary_msg
                }
                analysis = advisor.get_analysis(ai_ctx, symbol="코스피200 선물")
                send_message(chat_id, f"🤖 **AI 시장 분석**\n\n{analysis}")
        except Exception as e:
            send_message(chat_id, f"❌ 시장 종합 조회 실패: {e}")

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
        # Natural Language Handling (Chat Mode)
        # 1. Identify Intent/Asset
        text_lower = text.lower()
        code_to_check = None
        
        # Key-Value Mapper for Convenience
        asset_map = {
            # Stocks
            "samsung": "005930",
            "삼성전자": "005930",
            "삼성": "005930",
            "sk": "000660",
            "hynix": "000660",
            "하이닉스": "000660",
            "에스케이": "000660",
            "naver": "035420",
            "네이버": "035420",
            "카카오": "035720",
            "현대차": "005380",
            "현대자동차": "005380",
            # Samsung Futures (with and without space)
            "삼성 선물": "A1163000",
            "삼성선물": "A1163000",
            "samsung future": "A1163000",
            # KOSPI 200 Futures (with and without space)
            "kospi200": "101V6000",
            "kospi 200": "101V6000",
            "코스피200": "101V6000",
            "코스피 선물": "101V6000",
            "코스피선물": "101V6000",
            "지수 선물": "101V6000",
            "지수선물": "101V6000",
            "index future": "101V6000",
            "선물 가격": "101V6000",
            "선물": "101V6000",
            # Generic - default to Samsung stock
            "kospi": "005930",
            "코스피": "005930",
        }
        
        # Check map (longest key first to avoid partial matches)
        for key in sorted(asset_map.keys(), key=len, reverse=True):
            if key in text_lower:
                code_to_check = asset_map[key]
                break
        
        # Check explicit codes (simple regex-like check)
        if not code_to_check:
            for word in parts:
                if (word.startswith("A") or word.startswith("00") or word.startswith("101")) and len(word) >= 6:
                    code_to_check = word
                    break
        
        # 2. Fetch Data (if we found a code)
        market_data = None
        if code_to_check:
             market_data = get_price_data(code_to_check)
             send_message(chat_id, f"🧠 Thinking about `{code_to_check}`...")
        else:
             send_message(chat_id, "🧠 Thinking...")

        # 3. Call Gemini Chat
        response = advisor.get_chat_response(text, market_data, symbol=code_to_check if code_to_check else "General")
        send_message(chat_id, response)

def run_bot():
    offset = 0
    print(f"Bot polling started...")
    
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

# --- Main Entry ---
if __name__ == "__main__":
    # Initialize Global Instances
    print("Initializing Xing API...")
    trader = XingRestTrader()
    if not trader.get_access_token():
        print("Warning: Xing Token Failed. Bot will start but API calls may fail.")

    print("Building futures cache...")
    build_futures_cache(trader)

    print("Initializing Public Data Client...")
    public_data = PublicDataClient()

    print("Initializing Gemini Advisor...")
    advisor = GeminiAdvisor(GEMINI_API_KEY)
    
    # Initialize Realtime WebSocket Client
    print("Initializing Realtime WebSocket...")
    realtime_client = XingRealtimeClient()
    if realtime_client.start():
        print("Realtime WebSocket connected.")
    else:
        print("Warning: Realtime WebSocket failed. /realtime commands may not work.")

    # Start Alert Thread
    print("Starting Alert Monitor...")
    threading.Thread(target=check_alerts, daemon=True).start()
    
    run_bot()
