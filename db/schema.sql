
CREATE TABLE IF NOT EXISTS repos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url TEXT NOT NULL,
  status TEXT DEFAULT 'pending', -- pending|indexing|ready|failed
  error TEXT,
  metadata JSONB,
  indexed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  repo_id UUID REFERENCES repos(id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  start_line INT,
  end_line INT,
  chunk_type TEXT,   -- code|doc|config
  raw_text TEXT,
  embedding VECTOR(1024)
);

