import os
import requests
from dotenv import load_dotenv

load_dotenv()

r = requests.get("https://openrouter.ai/api/v1/models")
if r.status_code == 200:
    models = r.json()["data"]
    free_vision = [m["id"] for m in models if "free" in m["id"].lower() and m.get("architecture", {}).get("modality") != "text"]
    print("Free multimodal models:", free_vision)
else:
    print("Failed:", r.text)
