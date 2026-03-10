
import requests
import json
import time

class GeminiAdvisor:
    def __init__(self, api_key):
        self.api_key = api_key
        # Using gemini-1.5-flash for stable API availability
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        
        # Cache for recent identical intents to save API quota
        self._intent_cache = {}
        self._analysis_cache = {}

    def get_analysis(self, market_data, symbol="Unknown"):
        """
        Generates a trading scenario based on market data.
        """
        # ... (Existing logic) ...
        prompt = f"""
        You are an expert Futures Trader (Scalper/Day Trader).
        Current Date and Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        Provide a concise "Market Analysis & Trading Scenario" for {symbol}.
        
        Current Market Data:
        {json.dumps(market_data, indent=2)}

        Format your response exactly like this:
        1. **Trend**: [Bullish/Bearish/Neutral] because [Reason]
        2. **Key Levels**: Support [Price], Resistance [Price]
        3. **Scenario**:
           - **Bull Case**: If price breaks above [Price], BUY. Target: [Price].
           - **Bear Case**: If price breaks below [Price], SELL. Target: [Price].
        
        Keep it short (less than 150 words) and actionable.
        """
        return self._generate(prompt)

    def get_chat_response(self, user_text, market_data=None, symbol="Unknown"):
        """
        Handles natural language chat with optional market context.
        """
        context_str = ""
        if market_data:
            context_str = f"\nContext Market Data for {symbol}:\n{json.dumps(market_data, indent=2)}\n"
        
        prompt = f"""
        You are SP Ktrade Bot v1.2.2, an AI Trading Assistant.
        Identity: Bio-healthcare specialist business assistant & Quant derivatives trading expert.
        CURRENT VERSION: v1.2.2 (Strategic Master)
        Current Date and Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

        User Input: "{user_text}"
        {context_str}
        
        Instructions:
        - If the user asks for analysis or price, use the Context Market Data (if valid) to answer.
        - If the data is 0 or missing, mention that.
        - If the user asks general questions, answer helpfully.
        - You MUST identify as SP Ktrade Bot v1.2.1 in your greetings or footer.
        - Keep it concise and professional.
        """
        return self._generate(prompt)

    def analyze_intent(self, user_text):
        """
        Extracts user intent and target asset from natural language.
        Returns a JSON string containing {"action": "...", "target_code": "..."}
        Actions: "price", "market", "futures", "options", "chat"
        """
        prompt = f"""
        You are an NLP routing assistant for a Korean financial trading bot.
        Extract the user's intent from the following text: "{user_text}"
        
        Rules:
        1. Action MUST be one of: "price", "market", "night_market", "futures", "options", "web_search", "portfolio_strategy", "chat", "stock_analysis", "weekly_strategy".
        2. Target code MUST be a 6-to-8 character code like "005930" (Samsung) or "101V6000" (KOSPI 200). 
           - Map "삼성전자", "삼성", "samsung" to "005930"
           - Map "에스케이", "sk하이닉스", "hynix" to "000660"
           - Map "네이버", "naver" to "035420"
           - Map "코스피200", "지수", "선물" to "101V6000"
           - Map "삼성선물" to "A1163000"
           - For "web_search" actions, "target_code" should be the actual search keyword (e.g., "나스닥", "테슬라 주가").
           - If no specific code is mentioned, use "" (empty string).
        3. Intents:
           - Asking for a KOREAN company's current price/simple quote -> "price"
           - Asking for a deep analysis, historical trends, or future predictions of a specific stock -> "stock_analysis"
           - Asking for a general KOREAN market summary/overview (Daytime Focus) -> "market"
           - Specifically asking about "야간 선물", "야간 옵션", "야간 시장", "night market" -> "night_market"
           - Asking for KOSPI futures prices without specific code -> "futures"
           - Asking for KOSPI options prices -> "options"
           - Asking for US/Global markets, Crypto, specific News -> "web_search"
           - Providing a portfolio (e.g., holding 1 futures, 4 options) and asking for a pre-market strategy/scenario -> "portfolio_strategy"
           - Asking for a comprehensive WEEKLY analysis, weekend market summary, or specifically asking about KOSPI 200 + Weekly Options strategy -> "weekly_strategy"
           - Greetings, general internal bot questions -> "chat"
        
        Respond ONLY with a valid JSON object. No markdown formatting, no backticks.
        Example 1: {{"action": "price", "target_code": "005930"}}
        Example 2: {{"action": "night_market", "target_code": ""}}
        Example 3: {{"action": "web_search", "target_code": "테슬라 애플 주가"}}
        Example 4: {{"action": "portfolio_strategy", "target_code": ""}}
        Example 5: {{"action": "weekly_strategy", "target_code": ""}}
        Example 6: {{"action": "chat", "target_code": ""}}
        """
        
        import time
        
        # Check cache first
        # Very simple cache eviction (keep last 50 items)
        if len(self._intent_cache) > 50:
            self._intent_cache.clear()
            
        if user_text in self._intent_cache:
            cache_time, cached_result = self._intent_cache[user_text]
            if time.time() - cache_time < 1800: # Cache for 30 minutes (Increased from 5)
                return cached_result

        # We need to ensure we only get JSON back
        response_text = self._generate(prompt)
        
        # Clean up potential markdown formatting like ```json ... ```
        clean_text = response_text.replace("```json", "").replace("```", "").strip()
        
        if clean_text.startswith("{"):
            self._intent_cache[user_text] = (time.time(), clean_text)
            
        return clean_text

    def format_response(self, user_text, raw_data, data_type="price"):
        """
        Takes raw JSON/text data (e.g. from Xing REST or Brave Search) and formats it into a natural response.
        """
        prompt = f"""
        You are SP Ktrade Bot v1.2.2, a friendly and professional Korean AI trading assistant.
        Capabilities: Real-time portfolio monitoring (v1.2.2), Mock Trading (v1.2.2), Quantitative Strategy.
        CRITICAL: Never mention v1.1.0 or v1.2.1. You are strictly v1.2.2.
        Current Date and Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        The user asked: "{user_text}"
        
        Here is the raw '{data_type}' data retrieved from the system:
        {raw_data}
        
        Based ONLY on this data, provide a natural, conversational response in Korean.
        If the data indicates an error, contains 0s unexpectedly, or says "no results", explain that the information cannot be fetched right now.
        Use formatting like **bolding** to highlight important numbers or headlines. Keep it concise but informative.
        Finish the report with "SP Ktrade Bot v1.2.1 (Strategic Master)" footer.
        """
        return self._generate(prompt)

    def format_multi_timeframe_response(self, user_text, codes, daily_data, min5_data, min15_data, price_data=None, search_results=None):
        """
        Formats a complex response using multiple timeframes (Daily, 5m, 15m) for supply-demand analysis.
        Upgraded for v1.2.1 Strategic Master with ByPASS support.
        """
        prompt = f"""
        You are SP Ktrade Bot v1.2.2 (Strategic Master) - Bypass-enabled Analyst.
        Task: Provide a professional "Strategic Supply-Demand Analysis" (수급분석).
        Current Date and Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        Target Code: {codes}
        Current Price Info: {price_data}
        Search/News Context: {search_results}
        
        --- Market Data (OHLCV) ---
        Daily Candles: {daily_data if daily_data else "No daily data"}
        5-Minute Candles: {min5_data if min5_data else "No 5min data"}
        15-Minute Candles: {min15_data if min15_data else "No 15min data"}
        
        **ByPASS / Resilience Instructions (CRITICAL)**:
        - If technical candle data is missing (shown as 'No data' or empty []), DO NOT report an error.
        - Instead, use "Search/News Context" and "Current Price Info" to provide a 'Macro/News Correlation' analysis.
        - The goal is to NEVER stop the service. Bypass the data gap by focusing on broader market sentiment.
        
        Analysis Instructions:
        1. Multi-Timeframe Trend: Compare Daily vs. Intraday (if available).
        2. Supply-Demand: Evaluate volume/price behavior or news sentiment.
        3. Perspective: Home Trading System (HTS) expert analyst.
        4. Tone: Quantitative, professional (Korean). 
        5. Footer: "SP Ktrade Bot v1.2.1 (Strategic Master - Resilient Bypass Mode)"
        """
        return self._generate(prompt)

    def get_portfolio_strategy(self, user_portfolio_text, market_context):
        """
        Generates a pre-market scenario and trading strategy.
        Enhanced for v1.2.1 Strategic Master with ByPASS capabilities.
        """
        prompt = f"""
        You are SP Ktrade Bot v1.2.2, an elite "Strategic Master" quantitative analyst.
        Current Date and Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        The client has provided their portfolio/position:
        "{user_portfolio_text}"
        
        Market Context (May contain 'None' or 'Error' for some fields):
        {market_context}
        
        **ByPASS Instructions (CRITICAL)**:
        - If 'market_context' indicates that real-time or night session data is missing (e.g., "None", "fail", "No data"), do NOT report failure.
        - Instead, fulfill the request by analyzing the "Macro Environment" based on US market trends and recent global news found in the context.
        - Your report must always be actionable. Use phrases like "현재 야간 데이터 부재로 실시간 추적은 제한되나, [지표]를 기반으로 한 전략적 Bypass 시나리오는 다음과 같습니다."
        
        Format (v1.2.1 Strategic Master Style):
        **[코어봇 (CoreBot) v1.2.1 - Strategic Operations Report]**
        ... (Standard report structure follows) ...
        """
        return self._generate(prompt)

    def _generate(self, prompt, retries=3):
        import time
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        for attempt in range(retries):
            try:
                response = requests.post(self.url, json=payload, headers={"Content-Type": "application/json"}, timeout=120)
                
                # Try to parse JSON, handle potential parse errors
                try:
                    result = response.json()
                except Exception as je:
                    print(f"JSON Parse Error: {je}")
                    result = {"error": {"message": response.text}}

                if response.status_code == 200:
                    if 'candidates' in result and result['candidates']:
                         return result['candidates'][0]['content']['parts'][0]['text']
                    else:
                         return "AI returned no content."
                
                # Check for 429, 503, or specific error strings
                error_msg = result.get('error', {}).get('message', "")
                status_code = result.get('error', {}).get('status', str(response.status_code))
                
                is_transient_error = (
                    response.status_code in [429, 503] or 
                    "RESOURCE_EXHAUSTED" in error_msg or 
                    "quota" in error_msg.lower() or
                    "RESOURCE_EXHAUSTED" in status_code or
                    "UNAVAILABLE" in error_msg or
                    "high demand" in error_msg.lower() or
                    "UNAVAILABLE" in status_code
                )
                
                if is_transient_error:
                    # If primary model is exhausted, try to fallback to 8B once on first attempt
                    if attempt == 0 and ("429" in str(status_code) or "RESOURCE_EXHAUSTED" in error_msg):
                        if "gemini-1.5-flash" in self.url:
                            f8b_url = self.url.replace("gemini-1.5-flash", "gemini-1.5-flash-8b")
                            print(f"[Quota] Falling back to 8B model: {f8b_url}")
                            try:
                                f8b_resp = requests.post(f8b_url, json=payload, headers={"Content-Type": "application/json"}, timeout=120)
                                if f8b_resp.status_code == 200:
                                    f8b_result = f8b_resp.json()
                                    return f8b_result['candidates'][0]['content']['parts'][0]['text'] # Note: added 'content'
                            except Exception as f8be:
                                print(f"8B Fallback failed: {f8be}")

                    # Exponential Backoff: 70s, 140s... (Google Free Tier is per minute)
                    wait_time = 70 * (attempt + 1)
                    print(f"RATE LIMIT HIT: {error_msg}. Wait {wait_time}s (Attempt {attempt+1}/{retries})")
                    
                    if attempt < retries - 1:
                        time.sleep(wait_time)
                        continue
                    else:
                        return (
                            "[안내] **Gemini AI 모델 할당량 초과(Quota Exceeded)**\n\n"
                            "구글 무료 API 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.\n"
                            "(한도: 분당 약 15회 / 일일 1,500회)"
                        )
                
                else:
                    return f"[오류] **Gemini API**\n`{status_code}`: {error_msg}"
            
            except Exception as e:
                print(f"Request Exception (Attempt {attempt+1}): {e}")
                if attempt < retries - 1:
                    time.sleep(5)
                    continue
                return f"❌ AI Request Failed: {e}"
        return "❌ AI Request Failed after retries."
