import sys
from dotenv import load_dotenv
load_dotenv()
from db.client import get_connection
from fastapi.testclient import TestClient
from api.main import app

def main():
    # Find a ready repo
    repo_id = None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM repos WHERE status = 'ready' ORDER BY indexed_at DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                repo_id = row[0]
                
    if not repo_id:
        print("No ready repo found in DB.")
        sys.exit(1)
        
    print(f"Testing /ask endpoint against repo_id: {repo_id}")
    
    client = TestClient(app)
    response = client.post("/ask", json={
        "repo_id": str(repo_id),
        "question": "What files are in this repo?"
    })
    
    print("Status:", response.status_code)
    import json
    print("Response:", json.dumps(response.json(), indent=2))

if __name__ == "__main__":
    main()
