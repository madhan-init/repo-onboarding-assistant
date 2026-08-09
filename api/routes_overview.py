from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import json

from db.client import get_connection

router = APIRouter()

class OverviewResponse(BaseModel):
    status: str
    overview_text: Optional[str] = None
    folder_tree: Optional[List[str]] = None
    language_counts: Optional[Dict[str, int]] = None
    entry_points: Optional[List[str]] = None

@router.get("/overview/{repo_id}", response_model=OverviewResponse)
def get_overview(repo_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, metadata FROM repos WHERE id = %s", (repo_id,))
            row = cur.fetchone()
            
    if not row:
        raise HTTPException(status_code=404, detail="Repo not found")
        
    status, metadata_json = row
    
    if status == "ready" and metadata_json:
        try:
            metadata = metadata_json if isinstance(metadata_json, dict) else json.loads(metadata_json)
            return OverviewResponse(
                status=status,
                overview_text=metadata.get("overview"),
                folder_tree=metadata.get("folder_tree"),
                language_counts=metadata.get("language_counts"),
                entry_points=metadata.get("entry_points")
            )
        except Exception:
            return OverviewResponse(status="failed")
    
    return OverviewResponse(status=status)

@router.get("/snippet/{repo_id}")
def get_snippet(repo_id: str, file_path: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT raw_text FROM chunks WHERE repo_id = %s AND file_path = %s LIMIT 1",
                (repo_id, file_path)
            )
            row = cur.fetchone()
    if row:
        return {"content": row[0]}
    return {"content": "Snippet not available."}

@router.get("/file/{repo_id}")
def get_file(repo_id: str, file_path: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT start_line, end_line, raw_text FROM chunks WHERE repo_id = %s AND file_path = %s ORDER BY start_line ASC",
                (repo_id, file_path)
            )
            rows = cur.fetchall()
            
    if not rows:
        return {"content": "File not found in index."}
        
    lines = []
    last_end = 0
    
    for row in rows:
        start = row[0]
        end = row[1]
        text = row[2]
        chunk_lines = text.split('\n')
        
        # Remove trailing empty string from split if text ends with \n
        if len(chunk_lines) > 0 and chunk_lines[-1] == '':
            chunk_lines.pop()
            
        if start <= last_end:
            skip = last_end - start + 1
            lines.extend(chunk_lines[skip:])
        else:
            lines.extend(chunk_lines)
            
        last_end = end
        
    return {"content": '\n'.join(lines)}

