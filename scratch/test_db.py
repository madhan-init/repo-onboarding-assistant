from db.client import get_connection

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT repo_id, file_path, start_line, end_line, length(raw_text) FROM chunks LIMIT 20;")
        rows = cur.fetchall()
        print(f"Chunks: {len(rows)}")
        for r in rows:
            print(r)
