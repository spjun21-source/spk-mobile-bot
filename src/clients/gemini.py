
import requests
import json

class GeminiAdvisor:
    def __init__(self, api_key):
        self.api_key = api_key
        # Using the model we verified earlier
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite-001:generateContent?key={self.api_key}"

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

    def _generate(self, prompt):
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        try:
            response = requests.post(self.url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            result = response.json()
            if response.status_code == 200:
                if 'candidates' in result and result['candidates']:
                     return result['candidates'][0]['content']['parts'][0]['text']
                else:
                     return "AI returned no content."
            else:
                error_msg = result.get('error', {}).get('message', response.text)
                status = result.get('error', {}).get('status', response.status_code)
                return f"⚠️ **Gemini API Error**\n`{status}`: {error_msg}"
        except Exception as e:
            return f"❌ AI Request Failed: {e}"
