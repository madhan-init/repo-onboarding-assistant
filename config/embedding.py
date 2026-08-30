"""The embedding contract, in one place.

CLAUDE.md records 768 as load-bearing: it must equal VECTOR(768) in the schema and
match at every call site. This module is that single source; import it rather than
re-typing the constants.
"""
EMBED_URL = "https://api.fireworks.ai/inference/v1/embeddings"
EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
EMBED_DIM = 768
