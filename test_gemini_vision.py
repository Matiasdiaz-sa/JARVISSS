import os
import asyncio
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

async def main():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Look at the screen."},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call_123", "type": "function", "function": {"name": "ver_pantalla", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_123", "name": "ver_pantalla", "content": "Captured."},
        {"role": "user", "content": [{"type": "text", "text": "Image is here"}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="}}]}
    ]
    try:
        response = client.chat.completions.create(
            model="gemini-2.0-flash",
            messages=messages
        )
        print("Success:", response.choices[0].message.content)
    except Exception as e:
        print("Error:", e)

asyncio.run(main())
