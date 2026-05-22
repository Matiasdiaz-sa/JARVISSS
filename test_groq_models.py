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
    vision_models = [m["id"] for m in models if "vision" in m["id"].lower()]
    print("Vision models available on Groq:", vision_models)
else:
    print("Failed:", r.text)
