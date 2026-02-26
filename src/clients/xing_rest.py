import os
import requests
import json
import sys
import argparse

class XingRestTrader:
    def __init__(self, config_file="xing_config.json"):
        # Resolve path relative to the scratch directory (where config is located)
        if not os.path.isabs(config_file):
             # __file__ is in spk-mobile-bot/src/clients/
             # root is spk-mobile-bot's parent (scratch/)
             root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
             config_file = os.path.join(root_dir, config_file)
             
        try:
            with open(config_file, "r") as f:
                self.config = json.load(f)
        except FileNotFoundError:
            print(f"Config file '{config_file}' not found. Xing API disabled (Telegram bot will still run).")
            self.config = None
            self.base_url = "https://openapi.ls-sec.co.kr:8080"
            self.access_token = None
            return
        self.base_url = self.config.get("base_url", "https://openapi.ls-sec.co.kr:8080")
        self.access_token = None

    def get_access_token(self):
        if self.config is None:
            return False
        url = f"{self.base_url}/oauth2/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "client_credentials",
            "appkey": self.config["app_key"],
            "appsecretkey": self.config["app_secret"],
            "scope": "oob"
        }
        
        try:
            # print(f"Requesting token from {url}...")
            response = requests.post(url, headers=headers, data=data, verify=False) 
            
            if response.status_code == 200:
                result = response.json()
                self.access_token = result.get("access_token")
                # print("Token Access Success")
                return True
            else:
                print(f"Token Request Failed: {response.status_code}")
                # print(response.text)
                return False
        except Exception as e:
            print(f"Error getting token: {e}")
            return False

    def _get_price_generic(self, type, code):
        if not self.access_token:
            print("No access token.")
            return None
            
        if type == "stock":
            url = f"{self.base_url}/stock/market-data"
            tr_cd = "t1102"
            in_block = "t1102InBlock"
            out_block = "t1102OutBlock"
            code_field = "shcode"
        elif type == "future":
            url = f"{self.base_url}/futureoption/market-data"
            tr_cd = "t2101"
            in_block = "t2101InBlock"
            out_block = "t2101OutBlock"
            code_field = "focode" 
        else:
            return None

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Authorization": f"Bearer {self.access_token}",
            "tr_cd": tr_cd,
            "tr_cont": "N",
            "tr_cont_key": "",
        }
        
        body = {
            in_block: {
                code_field: code
            }
        }

        try:
            # print(f"Requesting {type} price for {code}...")
            response = requests.post(url, headers=headers, json=body, verify=False)
            
            if response.status_code == 200:
                result = response.json()
                if out_block in result:
                    data = result[out_block]
                    price = data.get("price")
                    open_price = data.get("open")
                    high_price = data.get("high")
                    low_price = data.get("low")
                    
                    return {
                        "price": price,
                        "open": open_price,
                        "high": high_price,
                        "low": low_price
                    }
                else:
                    print(f"No out_block in result: {result}")
                    return None
            else:
                print(f"Request Failed for {code}: {response.status_code}")
                print(f"Response: {response.text}")
                return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_stock_price(self, shcode):
        return self._get_price_generic("stock", shcode)

    def get_futures_price(self, shcode):
        return self._get_price_generic("future", shcode)

    def get_kospi200_futures_list(self):
        if not self.access_token:
            return []
        
        url = f"{self.base_url}/futureoption/market-data"
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Authorization": f"Bearer {self.access_token}",
            "tr_cd": "t8402", 
            "tr_cont": "N",
            "tr_cont_key": "",
        }
        body = { "t8402InBlock": { "dummy": "0" } }

        try:
            print("Requesting KOSPI 200 Futures List (t8402)...")
            response = requests.post(url, headers=headers, json=body, verify=False)
            if response.status_code == 200:
                result = response.json()
                if "t8402OutBlock" in result:
                    return result["t8402OutBlock"]
                else:
                    return []
            else:
                print(f"t8402 Request Failed: {response.status_code}")
                return []
        except Exception as e:
            print(f"Error getting KOSPI 200 list: {e}")
            return []

    def get_futures_code_list(self):
        # ... (Keep existing simplified logic or merge) ...
        # For simplicity, returning t8401 (Stock) + t8402 (Index) combined
        stock_futures = self._get_futures_code_list_t8401()
        index_futures = self.get_kospi200_futures_list()
        return index_futures + stock_futures

    def _get_futures_code_list_t8401(self):
        if not self.access_token:
            print("No access token.")
            return []

        url = f"{self.base_url}/futureoption/market-data"
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Authorization": f"Bearer {self.access_token}",
            "tr_cd": "t8401", 
            "tr_cont": "N",
            "tr_cont_key": "",
        }
        
        body = {
            "t8401InBlock": {
                "dummy": "0" 
            }
        }

        try:
            # print("Requesting Futures Code List (t8401)...")
            response = requests.post(url, headers=headers, json=body, verify=False)
            if response.status_code == 200:
                result = response.json()
                codes = []
                
                if "t8401OutBlock" in result:
                    # Dump full list to file for debugging
                    with open("futures_codes_dump.json", "w", encoding="utf-8") as dump_file:
                        json.dump(result["t8401OutBlock"], dump_file, ensure_ascii=False, indent=2)
                    # print(f"Dumped {len(result['t8401OutBlock'])} codes to futures_codes_dump.json")

                    for item in result["t8401OutBlock"]:
                        codes.append(item)
                    return codes
                else:
                    # print(f"No t8401OutBlock in response. Keys: {result.keys()}")
                    return []
            else:
                 # print(f"Code List Request Failed: {response.status_code}")
                 return []
        except Exception as e:
            print(f"Error getting code list: {e}")
            return []

    def place_futures_order(self, shcode, qty, price, buy_sell_type="2"): 
        account_no = self.config.get("account_no")
        if not account_no:
            print("Error: 'account_no' missing.")
            return None

        url = f"{self.base_url}/futureoption/order"
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Authorization": f"Bearer {self.access_token}",
            "tr_cd": "CFOAT00100", 
            "tr_cont": "N",
            "tr_cont_key": "",
        }
        
        body = {
            "CFOAT00100InBlock1": {
                "FnoIsuNo": shcode,
                "BnsTpCode": buy_sell_type, 
                "FnoOrdPrcPtnCode": "00", # Limit
                "FnoOrdPrc": price,
                "OrdQty": qty,
                "AcntNo": account_no,
                "Pwd": self.config.get("cert_pw", "0000"),
                "UserUserId": self.config.get("user_id")
            }
        }

        try:
            print(f"Placing Futures Order: {buy_sell_type} {qty} of {shcode} at {price}...")
            response = requests.post(url, headers=headers, json=body, verify=False)
            if response.status_code == 200:
                result = response.json()
                if "CFOAT00100OutBlock1" in result:
                    ord_no = result["CFOAT00100OutBlock1"]["OrdNo"]
                    print(f"Futures Order Placed! OrdNo: {ord_no}")
                    return result
                elif "rsp_msg" in result:
                    print(f"Futures Order Failed: {result['rsp_msg']}")
                    return result
                else:
                    print(f"Futures Order Failed (Unknown): {result}")
                    return result
            else:
                print(f"Futures Order Request Failed: {response.status_code}")
                return {"error": response.text, "status": response.status_code}
        except Exception as e:
            print(f"Error: {e}")
            return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LS Securities Xing API Trader")
    parser.add_argument("--mode", choices=["price", "order", "list", "test"], default="test", help="Operation mode")
    parser.add_argument("--code", help="Stock or Futures Code (e.g., 005930, 101H6000)")
    parser.add_argument("--type", choices=["stock", "future"], default="future", help="Asset type")
    parser.add_argument("--qty", type=int, default=1, help="Order Quantity")
    parser.add_argument("--price", help="Order Price (Limit)")
    parser.add_argument("--buy_sell", choices=["1", "2"], default="2", help="1=Sell, 2=Buy")
    
    args = parser.parse_args()

    trader = XingRestTrader()
    if trader.get_access_token():
        
        if args.mode == "test":
             # Run the original test sequence logic
            # 1. Get Stock Price Check
            stock_px = trader.get_stock_price("005930")
            if stock_px:
                print(f"Stock 005930 Price: {stock_px}")

            # 2. Get Futures Codes
            futures_list = trader.get_futures_code_list()
            print(f"Found {len(futures_list)} potential KOSPI 200 futures contracts.")
            
            valid_code = None
            current_price = None
            
            # Try to find the first valid one
            for item in futures_list:
                code = item.get("shcode")
                name = item.get("hname")
                
                # Additional filter to ensure it's the main Kospi200 Futures (not Spread)
                is_kospi200 = code and code.startswith("101") and len(code) == 8 and "SPREAD" not in name.upper()
                
                if is_kospi200:
                     print(f"Checking {code} ({name})...")
                     price = trader.get_futures_price(code)
                     if price:
                         current_price = price
                         valid_code = code
                         print(f"VALID CODE FOUND: {valid_code} Price: {current_price}")
                         break
            
            # Fallback if no KOSPI 200 found
            if not valid_code and len(futures_list) > 0:
                 print("KOSPI 200 Future not found in simulation. Using fallback.")
                 # Just check functionality with first implementation
                 pass

            # 3. Place Order (only if valid code found)
            if valid_code and current_price: 
                 try:
                     limit_price = str(round(float(current_price) * 0.9, 2)) # Buy 10% lower
                     trader.place_futures_order(valid_code, 1, limit_price, "2") 
                 except Exception as e:
                     print(f"Error calculating price: {e}")
            else:
                pass
                # print("No valid futures code found for order test.")

        elif args.mode == "price":
            if not args.code:
                print("Error: --code required for price mode.")
            else:
                if args.type == "stock":
                    px = trader.get_stock_price(args.code)
                else:
                    px = trader.get_futures_price(args.code)
                
                if px:
                    print(f"PRICE_RESULT: {px}")
                else:
                    print("PRICE_RESULT: None")

        elif args.mode == "list":
             codes = trader.get_futures_code_list()
             # Print simplified JSON list
             simplified = [{"code": c.get("shcode"), "name": c.get("hname")} for c in codes]
             print(json.dumps(simplified, ensure_ascii=False, indent=2))

        elif args.mode == "order":
            if not args.code or not args.price:
                print("Error: --code and --price required for order mode.")
            else:
                if args.type == "future":
                    trader.place_futures_order(args.code, args.qty, args.price, args.buy_sell)
                else:
                    print("Stock order not fully enabled in CLI yet.")
