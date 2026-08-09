import os
import logging
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from anthropic import Anthropic

from db.client import get_connection
from api.retrieval import search_chunks, build_context_block
from api.prompt import GROUNDING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
router = APIRouter()

class AskRequest(BaseModel):
    repo_id: str
    question: str

class Citation(BaseModel):
    file_path: str
    start_line: int
    end_line: int

class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]

def get_repo_status(repo_id: str) -> Optional[str]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM repos WHERE id = %s", (repo_id,))
            row = cur.fetchone()
            return row[0] if row else None

@router.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest):
    status = get_repo_status(request.repo_id)
    if not status:
        raise HTTPException(status_code=404, detail="Repo not found")
    if status != 'ready':
        raise HTTPException(status_code=400, detail=f"Repo is not ready. Current status: {status}")

    # 1. Retrieve chunks
    chunks = search_chunks(request.repo_id, request.question, top_k=8)
    
    if not chunks:
        return AskResponse(
            answer="not found in this repo",
            citations=[]
        )

    # 2. Build context
    context = build_context_block(chunks)
    system_prompt = GROUNDING_SYSTEM_PROMPT.replace("{context}", context)

    # 3. Call Claude
    try:
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=system_prompt,
            messages=[{"role": "user", "content": request.question}]
        )
        answer = response.content[0].text
    except Exception as e:
        logger.error(f"Failed to call Claude: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate answer: {str(e)}")

    # 4. Extract citations from the answer
    citation_pattern = re.compile(r'\[(.*?):(\d+)-(\d+)\]')
    matches = citation_pattern.findall(answer)
    
    citations = []
    seen = set()
    for match in matches:
        file_path, start_line, end_line = match
        sig = (file_path, int(start_line), int(end_line))
        if sig not in seen:
            seen.add(sig)
            citations.append(Citation(
                file_path=file_path,
                start_line=int(start_line),
                end_line=int(end_line)
            ))

    return AskResponse(answer=answer, citations=citations)
