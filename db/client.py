import os
import psycopg
from pgvector.psycopg import register_vector
from dotenv import load_dotenv

load_dotenv()

def get_connection(register=True):
    conn = psycopg.connect(os.environ.get("DATABASE_URL", "postgresql://repoguide:password@localhost:5432/repoguide"), autocommit=True)
    if register:
        try:
            register_vector(conn)
        except psycopg.ProgrammingError:
            pass # Vector extension not created yet
    return conn

def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    with open(schema_path, 'r') as f:
        schema_sql = f.read()

    with get_connection(register=False) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
            print("Database schema initialized successfully.")

if __name__ == "__main__":
    init_db()
