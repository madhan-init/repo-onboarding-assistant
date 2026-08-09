import uuid
import subprocess
import os
import sys
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.client import get_connection

router = APIRouter()

class IndexRequest(BaseModel):
    github_url: str

class IndexResponse(BaseModel):
    repo_id: str
    status: str

@router.post("/index", response_model=IndexResponse)
def index_repo(request: IndexRequest):
    repo_id = str(uuid.uuid4())
    
    # 1. Insert pending row
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO repos (id, url, status) VALUES (%s, %s, %s)",
                    (repo_id, request.github_url, 'pending')
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
        
    # 2. Spawn subprocess pointing to ingester/run.py
    try:
        log_file = open(f"/tmp/{repo_id}_ingest.log", "w")
        subprocess.Popen(
            [sys.executable, "ingester/run.py", repo_id, request.github_url],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True
        )
    except Exception as e:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE repos SET status = 'failed' WHERE id = %s", (repo_id,))
        raise HTTPException(status_code=500, detail=f"Failed to spawn ingester: {e}")

    return IndexResponse(repo_id=repo_id, status="pending")
