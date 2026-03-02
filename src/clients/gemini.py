
import requests
import json

class GeminiAdvisor:
    def __init__(self, api_key):
        self.api_key = api_key
        # Using gemini-flash-latest because it has standard Free Tier quotas (1,500 RPD).
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={self.api_key}"
        
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
        You are SP Ktrade Bot, an AI Trading Assistant.
        User Input: "{user_text}"
        {context_str}
        
        Instructions:
        - If the user asks for analysis or price, use the Context Market Data (if valid) to answer.
        - If the data is 0 or missing, mention that.
        - If the user asks general questions, answer helpfully.
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
        1. Action MUST be one of: "price", "market", "futures", "options", "web_search", "portfolio_strategy", "chat", "stock_analysis", "weekly_strategy".
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
           - Asking for a general KOREAN market summary/overview -> "market"
           - Asking for KOSPI futures prices without specific code -> "futures"
           - Asking for KOSPI options prices -> "options"
           - Asking for US/Global markets, Crypto, specific News -> "web_search"
           - Providing a portfolio (e.g., holding 1 futures, 4 options) and asking for a pre-market strategy/scenario -> "portfolio_strategy"
           - Asking for a comprehensive WEEKLY analysis, weekend market summary, or specifically asking about KOSPI 200 + Weekly Options strategy -> "weekly_strategy"
           - Greetings, general internal bot questions -> "chat"
        
        Respond ONLY with a valid JSON object. No markdown formatting, no backticks.
        Example 1: {{"action": "price", "target_code": "005930"}}
        Example 2: {{"action": "stock_analysis", "target_code": "005930"}}
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
            if time.time() - cache_time < 300: # Cache for 5 minutes
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
        You are SP Ktrade Bot, a friendly and professional Korean AI trading assistant.
        The user asked: "{user_text}"
        
        Here is the raw '{data_type}' data retrieved from the system:
        {raw_data}
        
        Based ONLY on this data, provide a natural, conversational response in Korean.
        If the data indicates an error, contains 0s unexpectedly, or says "no results", explain that the information cannot be fetched right now.
        Use formatting like **bolding** to highlight important numbers or headlines. Keep it concise but informative.
        """
        return self._generate(prompt)

    def get_portfolio_strategy(self, user_portfolio_text, market_context):
        """
        Generates a pre-market scenario and trading strategy based on the user's current holdings
        and broader market context (US indices, KOSPI summary).
        """
        prompt = f"""
        You are an elite quantitative analyst and derivatives trader advising a client in South Korea before the KOSPI market opens.
        
        The client has provided their current portfolio/position:
        "{user_portfolio_text}"
        
        Here is the overnight / pre-market context (US markets & KOSPI baseline):
        {market_context}
        
        Your task:
        1. **Market Diagnosis**: Briefly summarize the overnight US market trend and how it might impact the KOSPI open (Gap up / Gap down / Mixed).
        2. **Position Assessment**: Analyze the risks and opportunities for their specific holdings based on this expected open.
        3. **Tactical Scenarios**: Provide clear scenarios:
           - [Scenario A]: If the market opens strong, what should they do with their positions (e.g., hold futures, take profit on calls)?
           - [Scenario B]: If the market opens weak or reverses, where is the pain point (stop-loss / hedge recommendation)?
        
        Write the response in professional, structured, conversational Korean. Use bullet points and bold text for readability.
        """
        return self._generate(prompt)

    def _generate(self, prompt, retries=2):
        import time
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        import time
        for attempt in range(retries + 1):
            try:
                response = requests.post(self.url, json=payload, headers={"Content-Type": "application/json"}, timeout=60)
                result = response.json()
                if response.status_code == 200:
                    if 'candidates' in result and result['candidates']:
                         return result['candidates'][0]['content']['parts'][0]['text']
                    else:
                         return "AI returned no content."
                else:
                    error_msg = result.get('error', {}).get('message', response.text)
                    status = result.get('error', {}).get('status', response.status_code)
                    err_str = (error_msg or "") + str(result)
                    
                    # 할당량 초과 시 자동 재시도 로직
                    if "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower() or status == 429:
                        print(f"RATE LIMIT WARN: {err_str}")
                        if attempt == 0:
                            print(f"[Gemini API] 429 Rate limit hit. Waiting 65s to clear 1-minute window...")
                            time.sleep(65)
                            continue
                        elif attempt == 1:
                            print(f"[Gemini API] 429 Rate limit hit again. Waiting 10s...")
                            time.sleep(10)
                            continue
                        else:
                            return (
                                "[안내] **Gemini AI 모델 속도 제한(Rate Limit)**에 도달했습니다.\n\n"
                                "짧은 시간에 많은 분석을 요청하여 구글 서버가 일시적으로 차단했습니다.\n"
                                "잠시 후(약 1분) 다시 시도해 주세요. (무료 서버 한도: 분당 15요청)"
                            )
                    return f"[오류] **Gemini API**\n`{status}`: {error_msg}"
            except Exception as e:
                if attempt < retries:
                    time.sleep(5)
                    continue
                return f"[오류] AI Request Failed: {e}"
