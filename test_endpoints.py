import time
from fastapi.testclient import TestClient
from api.main import app

def main():
    client = TestClient(app)
    
    print("1. Testing POST /index")
    res1 = client.post("/index", json={"github_url": "https://github.com/octocat/Hello-World"})
    print("Status:", res1.status_code)
    data1 = res1.json()
    print("Response:", data1)
    
    if res1.status_code != 200:
        return
        
    repo_id = data1['repo_id']
    print(f"\n2. Polling GET /overview/{repo_id}")
    
    for _ in range(5):
        time.sleep(2)
        res2 = client.get(f"/overview/{repo_id}")
        data2 = res2.json()
        print(f"Status: {data2['status']}")
        if data2['status'] in ['ready', 'failed']:
            import json
            print("Final metadata:", json.dumps(data2, indent=2))
            break
            
if __name__ == "__main__":
    main()
