import threading
import time
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

# Global reference to main.py's helper
_get_price_data_func = None
_get_futures_func = None

class DataCacheHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Suppress HTTP logs to keep bot console clean
        
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "SPK Mobile Bot Shared Cache"}).encode('utf-8'))
            return

        # Fetch basic portfolio items on-demand via REST for fallback
        # CoreBot's portfolio_monitor.js expects a dictionary of symbols
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        response_data = {}
        
        try:
            if _get_price_data_func:
                # 1. Fetch Samsung Electronics
                s_px = _get_price_data_func("005930")
                if s_px:
                    response_data["005930"] = {
                        "price": s_px.get('price'),
                        "change": s_px.get('change', '0'),
                        "type": "Stock",
                        "name": "삼성전자"
                    }
                    
                # 2. Fetch KOSPI 200 Futures (Active Month)
                if _get_futures_func:
                    f_list = _get_futures_func()
                    if f_list:
                        main_f = f_list[0].get('shcode')
                        if main_f:
                            f_px = _get_price_data_func(main_f)
                            if f_px:
                                response_data[main_f] = {
                                    "price": f_px.get('price'),
                                    "bid": f_px.get('price'), # REST Fallback doesn't easily return orderbook unless t8411 is used
                                    "ask": f_px.get('price'),
                                    "type": "Futures",
                                    "name": f_list[0].get('hname', 'KOSPI200 선물')
                                }
        except Exception as e:
            print(f"[SharedCache] Error fetching fallback REST data: {e}")

        self.wfile.write(json.dumps(response_data).encode('utf-8'))

def start_shared_data_server(price_func, futures_list_func, port=18791):
    global _get_price_data_func, _get_futures_func
    _get_price_data_func = price_func
    _get_futures_func = futures_list_func
    
    def run_server():
        try:
            server = HTTPServer(('127.0.0.1', port), DataCacheHandler)
            print(f"✅ SPK Mobile Bot Shared Data Server started on port {port}")
            server.serve_forever()
        except OSError as e:
            print(f"⚠️ Could not start Shared Data Server on port {port}: {e}")
            
    threading.Thread(target=run_server, daemon=True).start()
