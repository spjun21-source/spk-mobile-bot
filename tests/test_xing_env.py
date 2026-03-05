
import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.clients.xing_rest import XingRestTrader

def test_connection():
    load_dotenv()
    print("Testing XingRestTrader with Env Vars...")
    trader = XingRestTrader()
    if trader.get_access_token():
        print("[OK] Access Token obtained successfully!")
        price = trader.get_stock_price("005930")
        if price:
            print(f"[OK] Real-time data for Samsung (005930): {price}")
        else:
            print("[Error] Failed to fetch price data.")
    else:
        print("[Error] Failed to obtain Access Token.")

if __name__ == "__main__":
    test_connection()
