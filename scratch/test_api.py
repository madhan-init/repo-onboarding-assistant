from db.client import get_connection
from api.routes_overview import get_file

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM repos LIMIT 1")
        repo_id = str(cur.fetchone()[0])
        
res = get_file(repo_id, 'agent/config.py')
print("Length of content:", len(res['content']))
print("Content snippet:", repr(res['content'][:100]))
