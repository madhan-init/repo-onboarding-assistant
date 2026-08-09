import os
from dotenv import load_dotenv
import anthropic

load_dotenv()
try:
    print("Key length:", len(os.environ.get("ANTHROPIC_API_KEY", "")))
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=10,
        messages=[{"role": "user", "content": "Hello"}]
    )
    print("Success:", response.content[0].text)
except Exception as e:
    print("Error:", repr(e))
