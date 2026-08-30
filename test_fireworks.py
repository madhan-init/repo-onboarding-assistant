import os
import requests
from dotenv import load_dotenv
load_dotenv()
api_key = os.environ.get("FIREWORKS_API_KEY")
url = "https://api.fireworks.ai/inference/v1/embeddings"
headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
data = {"model": "nomic-ai/nomic-embed-text-v1.5", "input": ["hello world"], "dimensions": 1024}
response = requests.post(url, headers=headers, json=data)
if response.status_code == 200:
    print("nomic 1024:", len(response.json()['data'][0]['embedding']))
else:
    print("nomic 1024:", response.status_code, response.text)

data2 = {"model": "accounts/fireworks/models/bge-m3", "input": ["hello world"]}
response2 = requests.post(url, headers=headers, json=data2)
if response2.status_code == 200:
    print("bge-m3:", len(response2.json()['data'][0]['embedding']))
else:
    print("bge-m3:", response2.status_code, response2.text)
