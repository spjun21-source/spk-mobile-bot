"""
공공데이터포털 파생상품시세정보 API Client
- 선물시세 조회 (getStockFuturesPriceInfo)
- 옵션시세 조회 (getOptionsPriceInfo)
- API Key: b54b56bbc01baee17e4a9a2a5a4011e84e7f20b7929ac65484f6ea69fdeb2526
- 유효기간: 2026-02-12 ~ 2028-02-12
"""

import requests
from datetime import datetime, timedelta

BASE_URL = "https://apis.data.go.kr/1160100/service/GetDerivativeProductInfoService"
SERVICE_KEY = "b54b56bbc01baee17e4a9a2a5a4011e84e7f20b7929ac65484f6ea69fdeb2526"


class PublicDataClient:
    def __init__(self, service_key=SERVICE_KEY):
        self.service_key = service_key
        self.session = requests.Session()

    def _request(self, endpoint, params):
        """공통 API 호출"""
        url = f"{BASE_URL}/{endpoint}"
        params["serviceKey"] = self.service_key
        params["resultType"] = "json"
        try:
            r = self.session.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            body = data.get("response", {}).get("body", {})
            items = body.get("items", {}).get("item", [])
            return {
                "totalCount": body.get("totalCount", 0),
                "items": items
            }
        except Exception as e:
            print(f"[PublicData] API Error: {e}")
            return {"totalCount": 0, "items": []}

    def _find_latest_date(self, endpoint, max_lookback=5, category=None):
        """데이터가 있는 가장 최근 거래일 자동 탐색"""
        dt = datetime.now()
        for _ in range(max_lookback):
            bas_dt = dt.strftime("%Y%m%d")
            params = {"basDt": bas_dt, "numOfRows": "1", "pageNo": "1"}
            if category:
                params["prdCtg"] = category
            result = self._request(endpoint, params)
            if result["totalCount"] > 0:
                return bas_dt
            dt -= timedelta(days=1)
        return (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    # ---- Futures ----

    def get_futures_prices(self, bas_dt=None, category=None, num_rows=20):
        """선물 시세 조회
        Args:
            bas_dt: 기준일 (YYYYMMDD), None이면 최근 거래일 자동 탐색
            category: 상품 카테고리 (예: '파생 선물 코스피200')
            num_rows: 조회 건수
        Returns:
            dict with 'date', 'totalCount', 'items'
        """
        endpoint = "getStockFuturesPriceInfo"
        if not bas_dt:
            bas_dt = self._find_latest_date(endpoint, category=category)
        params = {"basDt": bas_dt, "numOfRows": str(num_rows), "pageNo": "1"}
        if category:
            params["prdCtg"] = category
        result = self._request(endpoint, params)
        result["date"] = bas_dt
        return result

    def get_kospi200_futures(self, bas_dt=None):
        """코스피200 선물 전용 조회 (주간)"""
        return self.get_futures_prices(
            bas_dt=bas_dt,
            category="파생 선물 코스피200 (주간)",
            num_rows=15
        )

    # ---- Options ----

    def get_options_prices(self, bas_dt=None, category=None, num_rows=20):
        """옵션 시세 조회"""
        endpoint = "getOptionsPriceInfo"
        if not bas_dt:
            bas_dt = self._find_latest_date(endpoint, category=category)
        params = {"basDt": bas_dt, "numOfRows": str(num_rows), "pageNo": "1"}
        if category:
            params["prdCtg"] = category
        result = self._request(endpoint, params)
        result["date"] = bas_dt
        return result

    def get_kospi200_options(self, bas_dt=None, num_rows=30):
        """코스피200 옵션 조회 (콜/풋 모두)"""
        return self.get_options_prices(
            bas_dt=bas_dt,
            category="파생 옵션 코스피200",
            num_rows=num_rows
        )

    # ---- Summaries for AI Context ----

    def get_market_summary(self, bas_dt=None):
        """AI 분석용 종합 시장 요약 데이터"""
        futures = self.get_kospi200_futures(bas_dt)
        options = self.get_kospi200_options(bas_dt, num_rows=50)

        # Filter active futures (거래량 > 0)
        active_futures = [f for f in futures.get("items", [])
                          if int(f.get("trqu", 0)) > 0]

        # Split options into calls/puts and filter active ones
        active_options = [o for o in options.get("items", [])
                          if int(o.get("trqu", 0)) > 0]
        calls = [o for o in active_options if " C " in o.get("itmsNm", "")]
        puts = [o for o in active_options if " P " in o.get("itmsNm", "")]

        # Sort by volume desc
        calls.sort(key=lambda x: int(x.get("trqu", 0)), reverse=True)
        puts.sort(key=lambda x: int(x.get("trqu", 0)), reverse=True)

        return {
            "date": futures.get("date", "N/A"),
            "futures": active_futures,
            "calls_top": calls[:10],
            "puts_top": puts[:10],
            "total_futures": len(futures.get("items", [])),
            "total_options": len(options.get("items", [])),
        }

    # ---- Formatting Helpers ----

    @staticmethod
    def format_futures_table(data):
        """선물 시세 텔레그램 메시지 포맷"""
        items = data.get("items", [])
        if not items:
            return f"📊 선물 시세 조회 결과 없음 (기준일: {data.get('date', '?')})"

        lines = [f"📈 **선물 시세** (기준일: {data.get('date', '?')})"]
        lines.append(f"총 {data.get('totalCount', 0)}건")
        lines.append("")

        for item in items:
            name = item.get("itmsNm", "?").strip()
            clpr = item.get("clpr", "0")
            vs = item.get("vs", "0")
            trqu = item.get("trqu", "0")
            opnint = item.get("opnint", "0")

            # Direction arrow
            try:
                vs_val = float(vs)
                arrow = "🔴" if vs_val < 0 else "🔵" if vs_val > 0 else "⚪"
                vs_str = f"+{vs}" if vs_val > 0 else str(vs)
            except:
                arrow = "⚪"
                vs_str = vs

            lines.append(
                f"{arrow} `{name}`\n"
                f"   종가: **{clpr}** ({vs_str})\n"
                f"   거래량: {trqu:>10} | 미결제: {opnint}"
            )

        return "\n".join(lines)

    @staticmethod
    def format_options_table(data):
        """옵션 시세 텔레그램 메시지 포맷"""
        items = data.get("items", [])
        if not items:
            return f"📊 옵션 시세 조회 결과 없음 (기준일: {data.get('date', '?')})"

        # Split into calls and puts
        calls = [i for i in items if " C " in i.get("itmsNm", "")]
        puts = [i for i in items if " P " in i.get("itmsNm", "")]

        # Filter active (trqu > 0) and sort by volume
        active_calls = sorted(
            [c for c in calls if int(c.get("trqu", 0)) > 0],
            key=lambda x: int(x.get("trqu", 0)), reverse=True
        )[:8]
        active_puts = sorted(
            [p for p in puts if int(p.get("trqu", 0)) > 0],
            key=lambda x: int(x.get("trqu", 0)), reverse=True
        )[:8]

        lines = [f"📊 **옵션 시세** (기준일: {data.get('date', '?')})"]
        lines.append(f"총 {data.get('totalCount', 0)}건")

        if active_calls:
            lines.append("\n🔵 **콜 옵션 (거래량 상위)**")
            for o in active_calls:
                name = o.get("itmsNm", "?").strip()
                clpr = o.get("clpr", "0")
                trqu = o.get("trqu", "0")
                vlty = o.get("iptVlty", "-")
                lines.append(f"  `{name}` | {clpr} | 거래량:{trqu} | IV:{vlty}%")

        if active_puts:
            lines.append("\n🔴 **풋 옵션 (거래량 상위)**")
            for o in active_puts:
                name = o.get("itmsNm", "?").strip()
                clpr = o.get("clpr", "0")
                trqu = o.get("trqu", "0")
                vlty = o.get("iptVlty", "-")
                lines.append(f"  `{name}` | {clpr} | 거래량:{trqu} | IV:{vlty}%")

        if not active_calls and not active_puts:
            lines.append("\n거래된 옵션 없음")

        return "\n".join(lines)

    @staticmethod
    def format_market_summary(summary):
        """종합 시장 요약 텔레그램 포맷"""
        lines = [f"🏦 **파생상품 시장 종합** (기준일: {summary.get('date', '?')})"]

        # Futures section
        futures = summary.get("futures", [])
        if futures:
            lines.append("\n📈 **코스피200 선물**")
            for f in futures:
                name = f.get("itmsNm", "?").strip()
                clpr = f.get("clpr", "0")
                vs = f.get("vs", "0")
                trqu = f.get("trqu", "0")
                opnint = f.get("opnint", "0")
                try:
                    vs_val = float(vs)
                    arrow = "▼" if vs_val < 0 else "▲" if vs_val > 0 else "─"
                    vs_str = f"+{vs}" if vs_val > 0 else str(vs)
                except:
                    arrow = "─"
                    vs_str = vs
                lines.append(f"  {arrow} `{name}`: **{clpr}** ({vs_str}) 거래:{trqu} 미결제:{opnint}")

        # Top calls
        calls = summary.get("calls_top", [])[:5]
        if calls:
            lines.append("\n🔵 **콜 옵션 Top 5 (거래량 기준)**")
            for o in calls:
                name = o.get("itmsNm", "?").strip()
                clpr = o.get("clpr", "0")
                trqu = o.get("trqu", "0")
                lines.append(f"  `{name}` | 종가:{clpr} | 거래:{trqu}")

        # Top puts
        puts = summary.get("puts_top", [])[:5]
        if puts:
            lines.append("\n🔴 **풋 옵션 Top 5 (거래량 기준)**")
            for o in puts:
                name = o.get("itmsNm", "?").strip()
                clpr = o.get("clpr", "0")
                trqu = o.get("trqu", "0")
                lines.append(f"  `{name}` | 종가:{clpr} | 거래:{trqu}")

        return "\n".join(lines)


# --- Quick Test ---
if __name__ == "__main__":
    client = PublicDataClient()

    print("=== 코스피200 선물 ===")
    futures = client.get_kospi200_futures()
    print(client.format_futures_table(futures))

    print("\n=== 코스피200 옵션 ===")
    options = client.get_kospi200_options()
    print(client.format_options_table(options))

    print("\n=== 시장 종합 ===")
    summary = client.get_market_summary()
    print(client.format_market_summary(summary))
