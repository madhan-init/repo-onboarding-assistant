import os
import shutil
import git
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clone_repo(url: str, repo_id: str) -> str:
    target_dir = f"/tmp/{repo_id}"
    
    if os.path.exists(target_dir):
        logger.info(f"Directory {target_dir} already exists. Removing it.")
        shutil.rmtree(target_dir)

    logger.info(f"Cloning {url} into {target_dir}")
    try:
        git.Repo.clone_from(url, target_dir, depth=1)
        return target_dir
    except Exception as e:
        logger.error(f"Failed to clone {url}: {e}")
        raise e
