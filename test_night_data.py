from src.clients.xing_rest import XingRestTrader
import json

trader = XingRestTrader()
if trader.get_access_token():
    print("Fetching active futures list...")
    futures = trader.get_kospi200_futures_list()
    for f in futures:
        print(f"Code: {f.get('shcode')} | Name: {f.get('hname')}")
else:
    print("Failed to get token.")
