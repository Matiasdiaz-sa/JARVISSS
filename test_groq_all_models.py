import os
import requests
from dotenv import load_dotenv

load_dotenv()

headers = {
    "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"
}
r = requests.get("https://api.groq.com/openai/v1/models", headers=headers)
if r.status_code == 200:
    models = r.json()["data"]
    for m in models:
        print(m["id"])
else:
    print("Failed:", r.text)
