"""Cross-checks api.lexical against the LIVE Postgres parser.

The unit tests in test_lexical.py encode what we believe Postgres does. This file
verifies that belief against the real thing -- it is the check that caught the
`app.route` bug, where PG lexes a dotted name as one token but our tokenizer split
it, so a query for @app.route could never match the indexed lexeme.

Skips when Postgres isn't running, so the rest of the suite stays offline.
"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from api.lexical import tokenize, build_tsquery

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _psql(sql):
    r = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "repoguide",
         "-d", "repoguide", "-tAc", sql],
        capture_output=True, text=True, cwd=REPO, timeout=60,
    )
    if r.returncode != 0:
        pytest.skip("postgres not available")
    return "\n".join(l for l in r.stdout.splitlines() if "level=warning" not in l).strip()


@pytest.fixture(scope="module")
def pg():
    try:
        _psql("SELECT 1")
    except Exception:
        pytest.skip("postgres not available")
    return _psql


SAMPLES = [
    "send_file", "url_for", "BuildError", "before_request", "app.route(path)",
    "self.app.config", "MethodNotAllowed", "get_json()", "teardown_appcontext",
    "SERVER_NAME", "how do I return a response if not authenticated",
]


@pytest.mark.parametrize("text", SAMPLES)
def test_tokenizer_is_a_superset_of_postgres_lexemes(pg, text):
    """Every lexeme Postgres indexes must be producible by our query tokenizer.

    A superset is required, not equality: we deliberately emit both `app.route`
    and its parts so the query matches documents indexing either form. Missing a
    lexeme would mean a silently unmatchable query.
    """
    out = pg(f"SELECT string_agg(lexeme, ' ') FROM unnest(to_tsvector('simple', $${text}$$));")
    pg_lexemes = {l for l in out.split() if len(l) >= 2}
    ours = set(tokenize(text))
    assert pg_lexemes <= ours, f"tokenizer misses lexemes Postgres indexes: {pg_lexemes - ours}"


def test_dotted_query_actually_matches_a_dotted_document(pg):
    """End-to-end proof of the app.route fix, through to_tsquery itself."""
    q = build_tsquery("how does app.route work")
    matched = pg(
        f"SELECT to_tsvector('simple', $$@app.route('/x')$$) @@ to_tsquery('simple', $${q}$$);"
    )
    assert matched == "t"


def test_english_config_would_have_destroyed_this_query(pg):
    """Documents the reason 'simple' is mandatory, so nobody 'optimises' it later."""
    eng = pg("SELECT string_agg(lexeme,' ') FROM unnest(to_tsvector('english',"
             "$$how do I return a response if not authenticated$$));")
    for python_keyword in ("if", "not", "do"):
        assert python_keyword not in eng.split()
