import os
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

IGNORE_DIRS = {'.git', 'node_modules', 'dist', 'build', '.venv'}
# .rst matters: most Python projects (flask included) write their whole manual
# in it, and excluding it leaves the tool unable to answer any prose question.
ALLOW_EXTENSIONS = {'.py', '.js', '.ts', '.go', '.java', '.rb', '.md', '.rst', '.txt',
                    '.yaml', '.json', '.toml', '.sql', '.html', '.css'}
MAX_FILE_SIZE = 500 * 1024  # 500KB
CHUNK_SIZE = 100
OVERLAP = 10

def get_chunk_type(ext: str) -> str:
    if ext in {'.md', '.rst', '.txt'}:
        return 'doc'
    if ext in {'.json', '.yaml', '.toml'}:
        return 'config'
    return 'code'

def chunk_repo(target_dir: str) -> List[Dict]:
    chunks = []
    for root, dirs, files in os.walk(target_dir):
        # Filter directories in-place
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, target_dir)
            ext = os.path.splitext(file)[1].lower()

            if ext not in ALLOW_EXTENSIONS:
                continue

            try:
                if os.path.getsize(file_path) > MAX_FILE_SIZE:
                    continue

                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                chunk_type = get_chunk_type(ext)
                
                start = 0
                while start < len(lines):
                    end = min(start + CHUNK_SIZE, len(lines))
                    chunk_text = "".join(lines[start:end])
                    
                    if chunk_text.strip():
                        chunks.append({
                            'file_path': rel_path,
                            'start_line': start + 1,
                            'end_line': end,
                            'chunk_type': chunk_type,
                            'raw_text': chunk_text
                        })
                    
                    start += (CHUNK_SIZE - OVERLAP)
            except Exception as e:
                logger.warning(f"Failed to process {rel_path}: {e}")
    
    return chunks
