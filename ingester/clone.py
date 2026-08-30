import os
import shutil
import git
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clone_repo(url: str, repo_id: str, ref: str = None) -> str:
    target_dir = f"/tmp/{repo_id}"
    
    if os.path.exists(target_dir):
        logger.info(f"Directory {target_dir} already exists. Removing it.")
        shutil.rmtree(target_dir)

    logger.info(f"Cloning {url} into {target_dir}" + (f" at {ref}" if ref else ""))
    try:
        # depth=1 alone takes the default branch's HEAD; `branch` pins a tag,
        # which is what makes an ingest reproducible.
        kwargs = {"depth": 1}
        if ref:
            kwargs["branch"] = ref
        repo = git.Repo.clone_from(url, target_dir, **kwargs)
        logger.info(f"Cloned at {repo.head.commit.hexsha}")
        return target_dir
    except Exception as e:
        logger.error(f"Failed to clone {url}: {e}")
        raise e
