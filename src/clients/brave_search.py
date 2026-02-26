import requests

class BraveSearchClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.search.brave.com/res/v1/web/search"

    def search(self, query, count=3):
        """
        Interacts with the Brave Search API to fetch search results.
        Returns a summarized string of the top results to save tokens.
        """
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key
        }
        params = {
            "q": query,
            "count": count  # Keep it small for Gemini context
        }

        try:
            response = requests.get(self.base_url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                # Extract and format the web results
                results = data.get("web", {}).get("results", [])
                if not results:
                    return f"❌ '{query}'에 대한 검색 결과를 찾을 수 없습니다."

                summary_parts = []
                for idx, res in enumerate(results[:count]):
                    title = res.get('title', '제목 없음')
                    description = res.get('description', '설명 없음')
                    summary_parts.append(f"[{idx+1}] {title}\n요약: {description}")

                # Check if there are specific news results
                news_results = data.get("news", {}).get("results", [])
                if news_results:
                    summary_parts.append("\n📰 [관련 뉴스]")
                    for idx, res in enumerate(news_results[:2]): 
                        title = res.get('title', '제목 없음')
                        description = res.get('description', '설명 없음')
                        summary_parts.append(f"- {title}\n  {description}")

                return "\n".join(summary_parts)
                
            else:
                return f"⚠️ Brave Search API Error ({response.status_code}): {response.text}"
        except Exception as e:
            return f"❌ 검색 중 오류 발생: {e}"
