import json
import time
from src.utils.helpers import get_price_data, lookup_name
from src.clients.public_data import PublicDataClient

class NLPRouter:
    def __init__(self, bot_context):
        self.bot = bot_context

    def handle(self, chat_id, text):
        self.bot.send_message(chat_id, "🧠 분석 중입니다. (30초~1분 소요, 잠시만 기다려 주세요.)")
        
        try:
            intent_json = self.bot.advisor.analyze_intent(text)
            
            if intent_json.startswith("⚠️") or intent_json.startswith("[오류]") or intent_json.startswith("[안내]"):
                self.bot.send_message(chat_id, intent_json)
                return
                
            intent = json.loads(intent_json)
            action = intent.get("action", "chat")
            target_code = intent.get("target_code", "")
            
            print(f"Parsed Intent: Action={action}, Code={target_code}")
            
            if action == "price":
                if target_code:
                    data = get_price_data(self.bot.trader, target_code)
                    if data:
                        data['asset_name'] = lookup_name(target_code)
                        reply = self.bot.advisor.format_response(text, data, data_type="price")
                    else:
                        reply = f"[오류] `{target_code}`에 대한 가격 데이터를 찾을 수 없어요."
                else:
                    reply = "어떤 종목의 가격을 원하시는지 말씀해 주세요! (예: 삼성전자 가격 알려줘)"
            
            elif action == "stock_analysis":
                if target_code:
                    name = lookup_name(target_code)
                    self.bot.send_message(chat_id, f"📊 **{name}**(`{target_code}`) 최근 동향 및 추세 분석 중입니다...\n(인터넷 뉴스 검색 및 캔들 데이터 수집이 포함되어 잠시 소요됩니다.)")
                    
                    price_data = get_price_data(self.bot.trader, target_code) or {"error": f"No real-time data for {name}"}
                    daily_data, min5_data, min15_data = [], [], []
                    
                    if target_code == "005930" or target_code.startswith("101"):
                        stock_code = "005930"
                        daily_data = self.bot.trader.get_stock_chart_daily(stock_code, count=10)
                        min5_data = self.bot.trader.get_stock_chart_minute(stock_code, interval=5, count=10)
                        min15_data = self.bot.trader.get_stock_chart_minute(stock_code, interval=15, count=10)
                    
                    search_query = f"{name} 주식 주가 시세 장기 전망 분석"
                    search_results = self.bot.brave_client.search(search_query) if self.bot.brave_client else "인터넷 검색 모듈 비활성화"
                    reply = self.bot.advisor.format_multi_timeframe_response(text, f"{name}({target_code})", daily_data, min5_data, min15_data, price_data, search_results)
                else:
                    reply = "어떤 종목을 분석해 드릴까요? (예: 지난 주 삼성전자 주가 분석해줘)"
            
            elif action == "night_market":
                try:
                    summary = self.bot.public_data.get_market_summary()
                    futures_list = summary.get('futures', [])
                    if futures_list:
                        lines = []
                        for f in futures_list[:3]:
                            name, clpr, vs, mkp, hipr, lopr, trqu = f.get('itmsNm', '?'), f.get('clpr', '0'), f.get('vs', '0'), f.get('mkp', '0'), f.get('hipr', '0'), f.get('lopr', '0'), f.get('trqu', '0')
                            try: arrow = "+" if float(vs) >= 0 else ""
                            except: arrow = ""
                            lines.append(f"*{name}*\n  종가: *{clpr}* ({arrow}{vs})\n  시가: {mkp} / 고가: {hipr} / 저가: {lopr}\n  거래량: {int(trqu):,}\n")
                        calls, puts = summary.get('calls_top', []), summary.get('puts_top', [])
                        if calls or puts:
                            lines.append("\n*주요 옵션*")
                            lines.extend([f"  콜 {c.get('itmsNm','?')}: {c.get('clpr','?')} ({c.get('vs','?')})" for c in calls[:2]])
                            lines.extend([f"  풋 {p.get('itmsNm','?')}: {p.get('clpr','?')} ({p.get('vs','?')})" for p in puts[:2]])
                        bas_dt_str = futures_list[0].get('basDt', '')
                        date_display = f"{bas_dt_str[:4]}-{bas_dt_str[4:6]}-{bas_dt_str[6:]}" if len(bas_dt_str) == 8 else bas_dt_str
                        reply = f"야간 선물/옵션 시황 리포트\n(기준일: {date_display}, 조회: {time.strftime('%H:%M')})\n\n" + "\n".join(lines)
                    else:
                        reply = "야간 선물 데이터를 가져올 수 없습니다."
                except Exception as night_e:
                    reply = f"야간 시황 조회 실패: {night_e}"

            elif action == "futures":
                reply = self.bot.advisor.format_response(text, self.bot.public_data.get_kospi200_futures(), data_type="futures list")
                
            elif action == "options":
                reply = self.bot.advisor.format_response(text, self.bot.public_data.get_kospi200_options(), data_type="options list")
                
            elif action == "web_search":
                if target_code:
                    self.bot.send_message(chat_id, f"🌐 인터넷 검색 중: `{target_code}`...")
                    reply = self.bot.advisor.format_response(text, self.bot.brave_client.search(target_code), data_type="web search results")
                else:
                    reply = "무엇을 검색해 드릴까요? (예: 미국 나스닥 상황 알려줘)"

            elif action in ["portfolio_strategy", "market"]:
                self.bot.send_message(chat_id, ("📊 보유 포지션 기반 시나리오 분석 중..." if action == "portfolio_strategy" else "📊 실시간 장중 시황 및 전략 시나리오 분석 중...") + "\n(데이터 수집·AI 분석에 10초~30초 소요, 잠시만 기다려 주세요.)")
                
                us_market_context = self.bot.brave_client.search("간밤 미국 증시 마감 요약 주요 지수 특징주") if self.bot.brave_client else "미국 증시 검색 불가"
                
                import re
                tickers = re.findall(r"\b\d{6}\b", text)
                realtime_prices = {}
                for t in tickers:
                    px_data = get_price_data(self.bot.trader, t)
                    if px_data and px_data.get('price'): realtime_prices[t] = px_data['price']
                         
                try:
                    if "005930" not in realtime_prices:
                        s_px = get_price_data(self.bot.trader, "005930")
                        if s_px and s_px.get('price'): realtime_prices["005930"] = s_px['price']
                    
                    f_list = self.bot.trader.get_kospi200_futures_list()
                    if f_list:
                        main_f = f_list[0].get('shcode')
                        if main_f and main_f not in realtime_prices:
                            f_px = get_price_data(self.bot.trader, main_f)
                            if f_px and f_px.get('price'): realtime_prices[main_f] = f_px['price']
                except Exception: pass
                
                price_context = ""
                if realtime_prices:
                    from datetime import datetime
                    price_context = f"\n[현재 시간({datetime.now().strftime('%m-%d %H:%M')}) 기준 실시간 지표]\n" + "\n".join([f"- {lookup_name(k)} ({k}): {v:,}원" for k,v in realtime_prices.items()])

                try:kr_market_context = PublicDataClient.format_market_summary(self.bot.public_data.get_market_summary())
                except Exception as e: kr_market_context = f"한국 시장 요약 가져오기 실패: {e}"
                
                market_context = f"{price_context}\n\n[미국 증시 동향]\n{us_market_context}\n\n[국내 파생/현물 기초 데이터]\n{kr_market_context}"
                
                portfolio_input = text if action == "portfolio_strategy" else "단순 시황 요약 요청이므로 특정 포지션은 없음."
                reply = self.bot.advisor.get_portfolio_strategy(user_portfolio_text=portfolio_input, market_context=market_context)
                
            elif action == "weekly_strategy":
                self.bot.send_message(chat_id, "📊 주말 글로벌/국내 시황 및 다음 주 KOSPI200/위클리 옵션 전략을 분석 중입니다...\n(데이터 수집·AI 분석에 약 1분 소요됩니다.)")
                us_market_context = self.bot.brave_client.search("미국 나스닥 증시 주간 마감 요약 KOSPI 주간 전망") if self.bot.brave_client else "미국 증시 검색 불가"
                try: kr_market_context = PublicDataClient.format_market_summary(self.bot.public_data.get_market_summary())
                except Exception as e: kr_market_context = f"한국 시장 요약 데이터 실패: {e}"

                market_context = f"[미국 및 글로벌 증시 주간 동향]\n{us_market_context}\n\n[국내 KOSPI200/옵션 기초 상황]\n{kr_market_context}"
                reply = self.bot.advisor.get_portfolio_strategy(user_portfolio_text="KOSPI200 선물 1계약 양방향 타점, 위클리 옵션 콜 2계약 및 풋 2계약 대응 전략", market_context=market_context)
                
            else:
                market_data = get_price_data(self.bot.trader, target_code) if target_code else None
                reply = self.bot.advisor.get_chat_response(text, market_data, symbol=target_code if target_code else "General")
            
            self.bot.send_message(chat_id, reply)
            
        except json.JSONDecodeError:
            self.bot.send_message(chat_id, f"[오류] AI 서버 응답 오류:\n{intent_json.replace(chr(10060), '[X]')}")
        except Exception as e:
            import traceback; traceback.print_exc()
            self.bot.send_message(chat_id, f"[오류] {e}")
