import os
import psycopg
from pgvector.psycopg import register_vector
from dotenv import load_dotenv
import traceback
import sys

load_dotenv()

def get_connection(register=True):
    db_url = os.environ.get("DATABASE_URL", "postgresql://repoguide:password@localhost:5432/repoguide")
    # Mask password if printing
    safe_url = db_url
    if "@" in safe_url and ":" in safe_url:
        try:
            parts = safe_url.split("@")
            user_pass = parts[0].split("://")[1]
            safe_url = safe_url.replace(user_pass, "***:***")
        except:
            pass
    print(f"Connecting to database: {safe_url}")
    
    conn = psycopg.connect(db_url, autocommit=True)
    if register:
        try:
            register_vector(conn)
        except psycopg.ProgrammingError:
            pass # Vector extension not created yet
    return conn

def init_db():
    try:
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        with get_connection(register=False) as conn:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
                print("Database schema initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    init_db()

