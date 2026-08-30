DROP TABLE IF EXISTS chunks CASCADE;
DROP TABLE IF EXISTS repos CASCADE;
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
  chunk_label TEXT NOT NULL DEFAULT 'line100',  -- which chunker produced this row
  raw_text TEXT,
  embedding VECTOR(768),
  -- 'simple', never 'english': english strips is/not/in/and/or/if, which are
  -- Python keywords. Generated, so it backfills itself.
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', raw_text)) STORED
);

-- Full file content. `chunks` used to be the only record of it, so /file rebuilt
-- files by stitching chunks -- which cannot survive function-level chunking.
CREATE TABLE IF NOT EXISTS files (
  repo_id   UUID REFERENCES repos(id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  content   TEXT NOT NULL,
  sha       TEXT,
  PRIMARY KEY (repo_id, file_path)
);

CREATE INDEX IF NOT EXISTS chunks_tsv_idx   ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS chunks_label_idx ON chunks (repo_id, chunk_label);

