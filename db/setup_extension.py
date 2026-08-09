import os
import psycopg
import sys

def setup():
    user = os.environ.get("DB_SUPERUSER")
    password = os.environ.get("DB_SUPERUSER_PASSWORD")
    host = os.environ.get("DB_HOSTNAME")
    port = os.environ.get("DB_PORT")
    dbname = os.environ.get("DB_NAME", "db")
    
    if not all([user, password, host, port]):
        print("Superuser credentials not found in environment. Skipping automatic extension setup.", file=sys.stderr)
        return

    conn_str = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    print("Connecting as superuser to set up extensions...")
    
    try:
        with psycopg.connect(conn_str, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                print("Vector extension created successfully!")
    except Exception as e:
        print(f"Failed to create extension: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    setup()
