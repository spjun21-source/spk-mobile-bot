import json

# --- Futures Name Cache ---
futures_name_cache = {}

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
    if code in futures_name_cache:
        return futures_name_cache[code]
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

def get_price_data(trader_instance, code):
    """
    Helper to get price from Xing Trader.
    """
    is_stock = code.isdigit() and len(code) == 6
    if is_stock:
        data = trader_instance.get_stock_price(code)
        if data: return data
        return None
    
    data = trader_instance.get_futures_price(code)
    try:
        raw_price = str(data.get('price', '0')).replace(',', '').strip()
        price_val = float(raw_price)
    except:
        price_val = 0
        
    if data and price_val > 0:
        return data
        
    underlying_map = {
        "A1163000": "005930",
        "A1162000": "005930", 
        "101H6000": "005930",
        "A0163": "005930"
    }
    
    stock_code = underlying_map.get(code)
    if not stock_code and code.startswith("101"):
         stock_code = "005930"
    
    if stock_code:
        s_data = trader_instance.get_stock_price(stock_code)
        if s_data:
            s_data['_fallback_note'] = f"Derived from Stock {stock_code}"
            return s_data
            
    return data
