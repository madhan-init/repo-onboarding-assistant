import os
import json
import logging
from typing import Dict
import anthropic

from api.llm import complete

logger = logging.getLogger(__name__)

def classify_overview_error(raw: str) -> str:
    """Turn a provider exception into one short, actionable sentence.

    The overview is user-facing text. Writing a raw API exception into it -- which
    is what this module used to do -- renders a 404 JSON blob to users as if it
    were the repository description.
    """
    lowered = (raw or "").lower()
    if "workspace" in lowered and "not found" in lowered:
        return ("The Anthropic workspace was not found. Check ANTHROPIC_WORKSPACE_ID "
                "in .env matches a workspace in the account that issued the API key.")
    if "anthropic-workspace-id is required" in lowered:
        return "This Anthropic key is identity-linked; set ANTHROPIC_WORKSPACE_ID in .env."
    if "rate_limit" in lowered or "quota" in lowered or "429" in lowered:
        return "Anthropic rate limit exceeded. Wait a minute and re-index."
    if "authentication" in lowered or "401" in lowered or "x-api-key" in lowered:
        return "The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in .env."
    return "The overview could not be generated. See the ingester logs for details."


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
        prompt = (
            "Analyze this repository metadata and write a short overview structured "
            "exactly like this: 1. A simple overview about the project. 2. The core "
            "modules/folders. 3. What type of project it contains (e.g. web app, "
            "library, API, etc). Do not use markdown formatting like asterisks or "
            f"bold text. Metadata: {json.dumps(metadata)}"
        )
        result = complete(user=prompt, max_tokens=500)
        metadata['overview'] = result.text.strip()
        metadata['overview_model'] = result.model
    except Exception as e:
        # Leave `overview` unset so the frontend renders its own degraded state,
        # and keep the diagnosis in a separate field. The full exception goes to
        # the log, never to the user.
        logger.warning(f"Failed to generate overview: {e}")
        metadata['overview'] = None
        metadata['overview_error'] = classify_overview_error(str(e))

    return metadata
