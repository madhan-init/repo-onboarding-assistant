import os
import json
import logging
from typing import Dict
import anthropic

logger = logging.getLogger(__name__)

def generate_metadata(target_dir: str) -> Dict:
    folder_tree = []
    ext_counts = {}
    entry_points = []
    
    ENTRY_POINT_PATTERNS = {'main.py', 'app.py', 'index.js', 'server.js', 'main.go', 'manage.py'}

    for root, dirs, files in os.walk(target_dir):
        if '.git' in root or 'node_modules' in root:
            continue
            
        rel_root = os.path.relpath(root, target_dir)
        depth = rel_root.count(os.sep)
        
        # Depth limit logic can remain if we only want top-level files
        if depth > 2:
            continue
            
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext:
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
            
            folder_tree.append(os.path.join(rel_root, file).lstrip('./'))
            
            if file in ENTRY_POINT_PATTERNS and depth == 0:
                entry_points.append(os.path.join(rel_root, file))

    metadata = {
        'folder_tree': folder_tree,
        'language_counts': ext_counts,
        'entry_points': entry_points
    }
    
    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        prompt = f"Analyze this repository metadata and write a short overview structured exactly like this: 1. A simple overview about the project. 2. The core modules/folders. 3. What type of project it contains (e.g. web app, library, API, etc). Do not use markdown formatting like asterisks or bold text. Metadata: {json.dumps(metadata)}"
        
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        metadata['overview'] = response.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Failed to generate overview with Claude: {e}")
        err_msg = str(e)
        if "rate_limit" in err_msg.lower() or "quota" in err_msg.lower():
            metadata['overview'] = "Overview could not be generated: Claude API rate limit exceeded. Please wait a minute and re-index."
        else:
            metadata['overview'] = "Overview could not be generated. Check server logs."

    return metadata
