import os
import anthropic
from dotenv import load_dotenv
load_dotenv()
api_key = os.environ.get("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=api_key)
for model in ["claude-3-haiku-20240307", "claude-3-opus-20240229", "claude-2.1"]:
    try:
        response = client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "hi"}]
        )
        print(f"{model} works!")
    except Exception as e:
        print(f"{model} failed: {e}")
