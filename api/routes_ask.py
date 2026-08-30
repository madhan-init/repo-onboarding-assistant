import os
import logging
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional

from db.client import get_connection
from api.retrieval import search, build_context_block
from config.retrieval import DEFAULT_CONFIG, get as get_config
from api.llm import MODEL, get_client
from api.prompt import GROUNDING_SYSTEM_PROMPT
from eval.metrics import select_by_line_budget

logger = logging.getLogger(__name__)
router = APIRouter()

class AskRequest(BaseModel):
    repo_id: str
    question: str
    config: Optional[str] = None   # ladder row name; defaults to DEFAULT_CONFIG

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

    # 1. Retrieve chunks. Same entry point the eval harness uses, so the
    #    measured system and the shipped system cannot drift.
    try:
        config = get_config(request.config or DEFAULT_CONFIG)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    ranked = search(request.repo_id, request.question, config)
    chunks = select_by_line_budget(ranked, config.line_budget)
    
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
        client = get_client()
        response = client.messages.create(
            model=MODEL,
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
