from src.utils.helpers import lookup_name, get_price_data
from src.clients.public_data import PublicDataClient
import time

class CommandHandler:
    def __init__(self, bot_context):
        self.bot = bot_context

    def handle(self, chat_id, text, cmd, parts):
        if cmd == "/subscribe":
            position = text.replace("/subscribe", "").strip()
            if not position:
                self.bot.send_message(chat_id, "💡 사용법: `/subscribe [나의 포지션]`\n예시: `/subscribe 삼성전자 10주, 코스피200 선물 1개, 위클리 옵션 4계약(풋/콜) 매수·매도`\n매일 **05:00** 야간장 마감 분석, **08:50** 장전 포지션 시나리오 보고서를 자동 발송합니다.")
                return True
                
            subs = self.bot.scheduler.load_subscribers()
            subs[str(chat_id)] = position
            self.bot.scheduler.save_subscribers(subs)
            self.bot.send_message(chat_id, f"✅ **구독 완료!**\n저장된 포지션: `{position}`\n매일 05:00(야간장 마감), 08:50(장전 시나리오) 보고서를 보내드립니다.")
            return True
            
        elif cmd == "/unsubscribe":
            subs = self.bot.scheduler.load_subscribers()
            if str(chat_id) in subs:
                del subs[str(chat_id)]
                self.bot.scheduler.save_subscribers(subs)
                self.bot.send_message(chat_id, "[완료] **구독 취소 완료**\n더 이상 아침 리포트를 보내지 않습니다.")
            else:
                self.bot.send_message(chat_id, "현재 구독 중이 아닙니다.")
            return True

        elif cmd == "/id":
            self.bot.send_message(chat_id, f"👤 **My Chat ID:** `{chat_id}`")
            return True

        elif cmd in ["/start", "hello", "hi"]:
            msg = (
                "🤖 **SPK Mobile Bot v1.3.0 (Unified Operations)**\n"
                "실시간 종목 감시 및 전술적 매매 시그널 봇입니다.\n\n"
                "📋 **주요 명령어**\n"
                "`/price [종목코드]` - 실시간 호가/체결가 조회\n"
                "`/market` - 파생상품 종합 + AI분석 (v1.3.0)\n"
                "`/watch [종목코드]` - 자동 감시 등록\n"
                "`/list` - 감시 중인 종목 목록\n"
                "`/unwatch [종목코드]` - 감시 해제\n"
                "`/analyze [종목코드]` - 다중 타임프레임 AI 수급분석\n"
                "`/subscribe` - 장전/장마감 자동 브리핑 구독\n"
            )
            self.bot.send_message(chat_id, msg)
            return True

        elif cmd == "/watch":
            if len(parts) < 4:
                self.bot.send_message(chat_id, "Usage: `/watch [code] [>|<] [price]`\nEx: `/watch A1163000 > 168000`")
                return True
                
            code, condition = parts[1], parts[2]
            try: target = float(parts[3].replace(",", ""))
            except: 
                 self.bot.send_message(chat_id, "Price must be a number.")
                 return True
                 
            if condition not in ['>', '<']:
                 self.bot.send_message(chat_id, "Condition must be `>` or `<`.")
                 return True

            self.bot.alert_monitor.add_alert(chat_id, code, condition, target)
            self.bot.send_message(chat_id, f"✅ **Alert Set**\nWill notify when `{code}` {condition} {target}")
            return True

        elif cmd == "/list":
            self.bot.send_message(chat_id, "Fetching futures list...")
            codes = self.bot.trader.get_futures_code_list()
            if not codes:
                self.bot.send_message(chat_id, "No futures found.")
                return True

            index_futures, samsung_futures, other_futures = [], [], []
            for c in codes:
                shcode, hname = c.get("shcode", ""), c.get("hname", "")
                if not shcode: continue
                entry = f"`{shcode}`: {hname}"
                if shcode.startswith("101"): index_futures.append(entry)
                elif '삼성전자' in hname: samsung_futures.append(entry)
                else: other_futures.append(entry)

            msg_parts = []
            if index_futures: msg_parts.append("📈 **KOSPI 200 Index:**\n" + "\n".join(index_futures[:5]))
            if samsung_futures: msg_parts.append("🏢 **삼성전자 (Samsung):**\n" + "\n".join(samsung_futures[:5]))
            if other_futures: msg_parts.append("📋 **Others (Top 10):**\n" + "\n".join(other_futures[:10]))

            self.bot.send_message(chat_id, f"**Futures List ({len(codes)} total)**\n\n" + "\n\n".join(msg_parts))
            return True

        elif cmd == "/price":
            if len(parts) < 2:
                self.bot.send_message(chat_id, "Usage: `/price [code]`")
                return True
            code = parts[1].upper()
            data = get_price_data(self.bot.trader, code)
            
            if data:
                price = data.get('price', 0)
                name = lookup_name(code)
                fallback_line = f"\n⚠️ _{data.get('_fallback_note', '')}_" if data.get('_fallback_note') else ""
                
                if price == 0:
                     self.bot.send_message(chat_id, f"⚠️ **{name}** (`{code}`)\nPrice is 0 (Check Permissions)")
                else:
                     msg = (f"📊 **{name}** (`{code}`)\nPrice: **{price:,}**\nOpen: {data.get('open', 'N/A'):,}\nHigh: {data.get('high', 'N/A'):,}\nLow: {data.get('low', 'N/A'):,}{fallback_line}")
                     self.bot.send_message(chat_id, msg)
            else:
                self.bot.send_message(chat_id, f"[오류] Could not fetch data for `{code}`")
            return True

        elif cmd == "/analyze":
            if len(parts) < 2:
                self.bot.send_message(chat_id, "Usage: `/analyze [code]`")
                return True
            code = parts[1]
            self.bot.send_message(chat_id, f"🧠 **Gemini AI** is analyzing `{code}`...")
            
            data = get_price_data(self.bot.trader, code)
            if not data:
                self.bot.send_message(chat_id, f"[오류] No market data found for {code}. Cannot analyze.")
                return True
            
            try:
                if self.bot.public_data:
                    mkt = self.bot.public_data.get_market_summary()
                    futures_ctx = ["선물 {itmsNm}: 종가 {clpr} (전일비 {vs}) 거래량 {trqu} 미결제 {opnint}".format(**f) for f in mkt.get('futures', [])[:2]]
                    calls_ctx = "콜옵션 Top: " + ", ".join(f"{c.get('itmsNm','').strip()} 종가{c.get('clpr',0)} 거래{c.get('trqu',0)}" for c in mkt.get('calls_top', [])[:3])
                    puts_ctx = "풋옵션 Top: " + ", ".join(f"{p.get('itmsNm','').strip()} 종가{p.get('clpr',0)} 거래{p.get('trqu',0)}" for p in mkt.get('puts_top', [])[:3])
                    ctx_lines = futures_ctx + ([calls_ctx] if mkt.get('calls_top') else []) + ([puts_ctx] if mkt.get('puts_top') else [])
                    if ctx_lines: data['_derivatives_context'] = "\n".join(ctx_lines)
            except Exception: pass
                
            analysis = self.bot.advisor.get_analysis(data, symbol=code)
            self.bot.send_message(chat_id, f"🤖 **Strategy Scenario**\n\n{analysis}")
            return True

        elif cmd in ["/buy", "/sell"]:
            if len(parts) < 4:
                self.bot.send_message(chat_id, f"Usage: `{cmd} [code] [qty] [price]`")
                return True
            
            code, qty, price = parts[1], parts[2], parts[3]
            type_code = "2" if cmd == "/buy" else "1" 
            
            if not qty.isdigit():
                 self.bot.send_message(chat_id, "Quantity must be a number.")
                 return True

            self.bot.send_message(chat_id, f"⏳ Sending Order: {cmd.upper()} {qty} of {code} @ {price}...")
            result = self.bot.trader.place_futures_order(code, qty, price, type_code)
            
            if result and "CFOAT00100OutBlock1" in result:
                 ord_no = result["CFOAT00100OutBlock1"]["OrdNo"]
                 self.bot.send_message(chat_id, f"✅ **Order Placed!**\nNumber: `{ord_no}`\n{cmd.upper()} {qty} of {code} at {price}")
            elif result and "rsp_msg" in result:
                 self.bot.send_message(chat_id, f"[오류] Order Failed: {result['rsp_msg']}")
            else:
                 self.bot.send_message(chat_id, f"[오류] Order Failed (Unknown Error): {result}")
            return True

        elif cmd == "/realtime":
            if len(parts) < 2:
                self.bot.send_message(chat_id, "Usage: `/realtime [code]`\nEx: `/realtime 101V6000`")
                return True
            code = parts[1].upper()
            duration = min(int(parts[2]) if len(parts) > 2 else 10, 30)

            if not self.bot.realtime_client or not self.bot.realtime_client.is_connected():
                self.bot.send_message(chat_id, "⚠️ Realtime WebSocket not connected. Use `/rt_status` to check.")
                return True

            self.bot.send_message(chat_id, f"📡 **Live Feed** `{code}` for {duration}s...")
            collected = []

            from src.clients.xing_realtime import parse_futures_execution
            def on_exec(tr_cd, tr_key, body):
                collected.append(parse_futures_execution(body))

            self.bot.realtime_client.on_callback("FC0", on_exec)
            self.bot.realtime_client.subscribe("FC0", code)
            time.sleep(duration)
            self.bot.realtime_client.unsubscribe("FC0", code)

            if "FC0" in self.bot.realtime_client._callbacks:
                try: self.bot.realtime_client._callbacks["FC0"].remove(on_exec)
                except: pass

            if collected:
                lines = [f"{'🔴' if d.get('buysell') == '1' else '🔵' if d.get('buysell') == '2' else '⚪'} {d.get('time','')} | {d.get('price',''):>10} | Δ{d.get('change','')} | Vol:{d.get('volume','')}" for d in collected[-15:]]
                self.bot.send_message(chat_id, f"📊 **{code} Execution Feed** ({len(collected)} ticks)\n```\n" + "\n".join(lines) + "\n```")
            else:
                self.bot.send_message(chat_id, f"⚠️ No data received for `{code}` in {duration}s.\n(Market may be closed: 09:00-15:45 KST)")
            return True

        elif cmd == "/orderbook":
            if len(parts) < 2:
                self.bot.send_message(chat_id, "Usage: `/orderbook [code]`\nEx: `/orderbook 101V6000`")
                return True
            code = parts[1].upper()

            if not self.bot.realtime_client or not self.bot.realtime_client.is_connected():
                self.bot.send_message(chat_id, "⚠️ Realtime WebSocket not connected.")
                return True

            self.bot.send_message(chat_id, f"📋 Fetching orderbook for `{code}`...")
            orderbook = [None]

            from src.clients.xing_realtime import parse_futures_orderbook
            def on_ob(tr_cd, tr_key, body):
                orderbook[0] = parse_futures_orderbook(body)

            self.bot.realtime_client.on_callback("FH0", on_ob)
            self.bot.realtime_client.subscribe("FH0", code)
            time.sleep(3)
            self.bot.realtime_client.unsubscribe("FH0", code)

            if "FH0" in self.bot.realtime_client._callbacks:
                try: self.bot.realtime_client._callbacks["FH0"].remove(on_ob)
                except: pass

            if orderbook[0]:
                ob = orderbook[0]
                lines = ["  매도(Ask)     수량  │  매수(Bid)     수량", "  ───────────  ─────  │  ───────────  ─────"]
                for i in range(5, 0, -1):
                    lines.append(f"  {ob.get(f'ask{i}', '-'):>10}  {ob.get(f'ask{i}_qty', '-'):>5}  │  {ob.get(f'bid{i}', '-'):>10}  {ob.get(f'bid{i}_qty', '-'):>5}")
                self.bot.send_message(chat_id, f"📋 **{code} Orderbook**\n```\n" + "\n".join(lines) + "\n```")
            else:
                self.bot.send_message(chat_id, f"⚠️ No orderbook data for `{code}`.\n(Market may be closed)")
            return True

        elif cmd == "/market":
            self.bot.send_message(chat_id, "🏦 시장 종합 분석 중... (공공데이터 + AI)")
            try:
                summary = self.bot.public_data.get_market_summary()
                summary_msg = PublicDataClient.format_market_summary(summary)
                self.bot.send_message(chat_id, summary_msg)

                futures_data = summary.get('futures', [])
                if futures_data and self.bot.advisor:
                    live_msg = ""
                    live_f_px = 0
                    try:
                        from datetime import datetime
                        f_list = self.bot.trader.get_kospi200_futures_list()
                        if f_list:
                            main_f_code = f_list[0].get('shcode')
                            f_px = get_price_data(self.bot.trader, main_f_code)
                            if f_px and f_px.get('price'):
                                live_f_px = float(f_px['price'])
                                live_msg += f"- 코스피200 선물({main_f_code}): {f_px['price']}\n"
                        s_px = get_price_data(self.bot.trader, "005930")
                        if s_px and s_px.get('price'): live_msg += f"- 삼성전자(005930): {s_px['price']}\n"
                        if live_msg: live_msg = f"\n[실시간 시장 지표 - {datetime.now().strftime('%m-%d %H:%M')}]\n" + live_msg
                    except Exception: pass

                    main_f = futures_data[0]
                    ai_ctx = {
                        'price': live_f_px if live_f_px > 0 else float(main_f.get('clpr', 0)),
                        'open': float(main_f.get('mkp', 0)),
                        'high': float(main_f.get('hipr', 0)),
                        'low': float(main_f.get('lopr', 0)),
                        '_derivatives_context': live_msg + "\n" + summary_msg if live_msg else summary_msg
                    }
                    analysis = self.bot.advisor.get_analysis(ai_ctx, symbol="코스피200 선물")
                    self.bot.send_message(chat_id, f"🤖 **AI 시장 분석**\n\n{analysis}")
            except Exception as e:
                self.bot.send_message(chat_id, f"[오류] 시장 종합 조회 실패: {e}")
            return True

        elif cmd == "/rt_status":
            if self.bot.realtime_client:
                from src.clients.xing_realtime import TR_DESCRIPTIONS
                connected = self.bot.realtime_client.is_connected()
                subs = list(self.bot.realtime_client._subscriptions.keys())
                msg = f"{'🟢' if connected else '🔴'} **Realtime WebSocket**\nConnected: **{connected}**\nServer: `{self.bot.realtime_client.ws_url}`\nActive Subscriptions: {len(subs)}\n"
                for tr_cd, tr_key in subs:
                    msg += f"  • `{tr_cd}` ({TR_DESCRIPTIONS.get(tr_cd, tr_cd)}) / `{tr_key}`\n"
                self.bot.send_message(chat_id, msg)
            else:
                self.bot.send_message(chat_id, "🔴 Realtime client not initialized.")
            return True

        return False # Not a recognized command
