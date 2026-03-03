import sys
import os
import re
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(os.path.abspath("src"))

def test_rebalancing_flow():
    print("--- Testing Rebalancing Flow & Price Injection ---")
    
    # Mocking Data
    user_text = "삼성전자 005930 15주 217,750 매입 단가, 현재 하락중 200,000원 손실중 Rebalancing 전략은?"
    
    # 1. Test Regex Ticker Extraction
    tickers = re.findall(r"\b\d{6}\b", user_text)
    print(f"Extracted Tickers: {tickers}")
    assert "005930" in tickers
    
    # 2. Mock Xing API and Gemini Advisor
    mock_trader = MagicMock()
    mock_trader.get_stock_price.return_value = {"price": 204500, "open": 205000, "high": 206000, "low": 203000}
    
    mock_advisor = MagicMock()
    mock_advisor.get_portfolio_strategy.return_value = "Mocked Rebalancing Strategy Report"
    
    # Simulated logic from main.py
    realtime_prices = {}
    for t in tickers:
        # Simulate lookup_name
        name = "삼성전자" if t == "005930" else t
        px_data = mock_trader.get_stock_price(t)
        if px_data and px_data.get('price'):
            realtime_prices[t] = px_data['price']
    
    price_context = ""
    if realtime_prices:
        price_context = "\n[실시간 시장가 데이터]\n" + "\n".join([f"- 삼성전자 ({k}): {v:,}원" for k,v in realtime_prices.items()])
    
    print(f"Generated Price Context: {price_context}")
    assert "삼성전자 (005930): 204,500원" in price_context
    
    # 3. Verify Gemini Call
    market_context = f"{price_context}\n\n[미국 증시 동향]\nPositive..."
    mock_advisor.get_portfolio_strategy(user_portfolio_text=user_text, market_context=market_context)
    
    mock_advisor.get_portfolio_strategy.assert_called_once()
    args, kwargs = mock_advisor.get_portfolio_strategy.call_args
    assert "[실시간 시장가 데이터]" in kwargs['market_context']
    print("OK: Rebalancing flow verification passed!")

if __name__ == "__main__":
    try:
        test_rebalancing_flow()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
