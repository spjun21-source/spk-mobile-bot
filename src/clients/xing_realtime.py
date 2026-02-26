"""
LS Securities (Xing) WebSocket Real-time Data Client
Subscribes to futures/options real-time market data via WebSocket.

TR Codes:
  FC0 - 선물주구분체결 (Futures Execution)
  FH0 - 선물주구분호가 (Futures Orderbook, 5-depth)
  OC0 - KOSPI200옵션체결 (Options Execution)
  OH0 - KOSPI200옵션호가 (Options Orderbook)
"""
import os
import json
import threading
import time
import ssl
import websocket
from .xing_rest import XingRestTrader


# --- TR Code Descriptions ---
TR_DESCRIPTIONS = {
    "FC0": "선물체결 (Futures Execution)",
    "FH0": "선물호가 (Futures Orderbook)",
    "OC0": "옵션체결 (Options Execution)",
    "OH0": "옵션호가 (Options Orderbook)",
}


class XingRealtimeClient:
    """WebSocket client for LS Securities real-time data."""

    WS_URL_REAL = "wss://openapi.ls-sec.co.kr:9443/websocket"
    WS_URL_SIM  = "wss://openapi.ls-sec.co.kr:29443/websocket"

    def __init__(self, config_file="xing_config.json", simulation=False):
        if not os.path.isabs(config_file):
             # __file__ is in spk-mobile-bot/src/clients/
             # root is spk-mobile-bot's parent (scratch/)
             root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
             config_file = os.path.join(root_dir, config_file)
        self.trader = XingRestTrader(config_file)
        self.access_token = None
        self.ws = None
        self.ws_url = self.WS_URL_SIM if simulation else self.WS_URL_REAL
        self.simulation = simulation
        self._running = False
        self._thread = None
        self._subscriptions = {}  # key: (tr_cd, tr_key) -> True
        self._callbacks = {}     # key: tr_cd -> [callback_fn, ...]
        self._lock = threading.Lock()
        self._connected = threading.Event()

    def authenticate(self):
        """Get access token via REST API."""
        if self.trader.get_access_token():
            self.access_token = self.trader.access_token
            print(f"[Realtime] Token acquired.")
            return True
        print("[Realtime] Failed to get access token.")
        return False

    def on_callback(self, tr_cd, callback):
        """Register a callback for a TR code. callback(tr_cd, tr_key, data)"""
        with self._lock:
            if tr_cd not in self._callbacks:
                self._callbacks[tr_cd] = []
            self._callbacks[tr_cd].append(callback)

    def subscribe(self, tr_cd, tr_key):
        """Subscribe to a real-time data feed."""
        key = (tr_cd, tr_key)
        if key in self._subscriptions:
            print(f"[Realtime] Already subscribed: {tr_cd}/{tr_key}")
            return

        msg = {
            "header": {
                "token": self.access_token,
                "tr_type": "3"   # 3 = subscribe
            },
            "body": {
                "tr_cd": tr_cd,
                "tr_key": tr_key
            }
        }

        if self.ws and self._connected.is_set():
            self.ws.send(json.dumps(msg))
            self._subscriptions[key] = True
            desc = TR_DESCRIPTIONS.get(tr_cd, tr_cd)
            print(f"[Realtime] Subscribed: {desc} / {tr_key}")
        else:
            print(f"[Realtime] Not connected. Queuing subscription: {tr_cd}/{tr_key}")
            self._subscriptions[key] = False  # Queued, will send on connect

    def unsubscribe(self, tr_cd, tr_key):
        """Unsubscribe from a real-time data feed."""
        key = (tr_cd, tr_key)
        if key not in self._subscriptions:
            return

        msg = {
            "header": {
                "token": self.access_token,
                "tr_type": "4"   # 4 = unsubscribe
            },
            "body": {
                "tr_cd": tr_cd,
                "tr_key": tr_key
            }
        }

        if self.ws and self._connected.is_set():
            self.ws.send(json.dumps(msg))
        del self._subscriptions[key]
        print(f"[Realtime] Unsubscribed: {tr_cd}/{tr_key}")

    def _on_open(self, ws):
        print(f"[Realtime] WebSocket connected to {self.ws_url}")
        self._connected.set()

        # Re-send any queued or existing subscriptions
        for (tr_cd, tr_key), sent in list(self._subscriptions.items()):
            if not sent:
                msg = {
                    "header": {
                        "token": self.access_token,
                        "tr_type": "3"
                    },
                    "body": {
                        "tr_cd": tr_cd,
                        "tr_key": tr_key
                    }
                }
                ws.send(json.dumps(msg))
                self._subscriptions[(tr_cd, tr_key)] = True
                print(f"[Realtime] Re-subscribed: {tr_cd}/{tr_key}")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            # Some messages may be raw text
            print(f"[Realtime] Raw message: {message[:200]}")
            return

        # Check for header info (subscription confirmations, errors)
        header = data.get("header", {})
        body = data.get("body", {})

        tr_cd = header.get("tr_cd", body.get("tr_cd", ""))
        tr_key = body.get("tr_key", "")

        # Response to subscription request
        if "rsp_cd" in header:
            rsp_cd = header.get("rsp_cd", "")
            rsp_msg = header.get("rsp_msg", "")
            if rsp_cd == "0000" or rsp_cd.startswith("0"):
                print(f"[Realtime] ✅ {tr_cd}/{tr_key}: {rsp_msg}")
            else:
                print(f"[Realtime] [X] {tr_cd}/{tr_key}: [{rsp_cd}] {rsp_msg}")
            return

        # Real-time data arrived — dispatch to callbacks
        with self._lock:
            callbacks = self._callbacks.get(tr_cd, [])

        for cb in callbacks:
            try:
                cb(tr_cd, tr_key, body)
            except Exception as e:
                print(f"[Realtime] Callback error for {tr_cd}: {e}")

    def _on_error(self, ws, error):
        print(f"[Realtime] Error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self._connected.clear()
        print(f"[Realtime] Disconnected. Code={close_status_code}, Msg={close_msg}")

        # Auto-reconnect if still running
        if self._running:
            print("[Realtime] Reconnecting in 5 seconds...")
            # Mark all subscriptions as not-sent for re-subscribe
            for key in self._subscriptions:
                self._subscriptions[key] = False
            time.sleep(5)
            self._connect()

    def _connect(self):
        """Internal: create and run WebSocket."""
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def start(self):
        """Start the WebSocket connection in a background thread."""
        if not self.access_token:
            if not self.authenticate():
                return False

        self._running = True
        self._thread = threading.Thread(target=self._connect, daemon=True)
        self._thread.start()

        # Wait for connection
        if self._connected.wait(timeout=10):
            print("[Realtime] Ready.")
            return True
        else:
            print("[Realtime] Connection timeout.")
            return False

    def stop(self):
        """Stop the WebSocket connection."""
        self._running = False
        if self.ws:
            self.ws.close()
        if self._thread:
            self._thread.join(timeout=5)
        print("[Realtime] Stopped.")

    def is_connected(self):
        return self._connected.is_set()


# --- Helper: Parse common fields from FC0 (futures execution) ---
def parse_futures_execution(body):
    """Parse FC0 body into a readable dict."""
    # FC0 OutBlock fields (common ones)
    return {
        "code": body.get("futcode", body.get("tr_key", "")),
        "price": body.get("price", body.get("close", "")),
        "change": body.get("change", ""),
        "diff": body.get("diff", body.get("drate", "")),
        "volume": body.get("cvolume", body.get("volume", "")),
        "time": body.get("chetime", body.get("time", "")),
        "buysell": body.get("cgubun", ""),  # 1=sell, 2=buy
        "open": body.get("open", ""),
        "high": body.get("high", ""),
        "low": body.get("low", ""),
        "total_volume": body.get("volume", ""),
    }


def parse_futures_orderbook(body):
    """Parse FH0 body into a readable dict (5-level depth)."""
    result = {
        "code": body.get("futcode", body.get("tr_key", "")),
    }
    # 5-level ask/bid
    for i in range(1, 6):
        result[f"ask{i}"] = body.get(f"offerho{i}", "")
        result[f"ask{i}_qty"] = body.get(f"offerrem{i}", "")
        result[f"bid{i}"] = body.get(f"bidho{i}", "")
        result[f"bid{i}_qty"] = body.get(f"bidrem{i}", "")
    return result
