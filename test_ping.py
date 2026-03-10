import urllib.request
import json
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('GEMINI_API_KEY')

if not api_key:
    print("Error: GEMINI_API_KEY not found in .env")
    exit(1)

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
payload = json.dumps({"contents": [{"parts": [{"text": "Hello, ping!"}]}]}).encode('utf-8')
headers = {'Content-Type': 'application/json'}

print("Sending ping to Gemini API...")
try:
    req = urllib.request.Request(url, data=payload, headers=headers)
    response = urllib.request.urlopen(req, timeout=10)
    result = json.loads(response.read().decode('utf-8'))
    print("\n[SUCCESS] Connection established! Response:")
    print(result['candidates'][0]['content']['parts'][0]['text'])
except Exception as e:
    print(f"\n[FAILED] Could not connect to Gemini API.")
    print(f"Error details: {e}")
