import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from api.lexical import tokenize, build_tsquery


# --- tokenize must mirror Postgres's 'simple' parser -------------------------
# Measured on PG 16.14:
#   to_tsvector('simple','send_file')  -> 'file':2 'send':1   (underscore splits)
#   to_tsvector('simple','BuildError') -> 'builderror':1      (camelCase does not)

def test_splits_snake_case_like_postgres():
    assert tokenize("send_file") == ["send", "file"]

def test_does_not_split_camel_case_like_postgres():
    assert tokenize("BuildError") == ["builderror"]

def test_lowercases():
    assert tokenize("URL_For") == ["url", "for"]

def test_splits_on_punctuation():
    assert tokenize("get_json()") == ["get", "json"]

def test_dotted_names_emit_both_forms():
    """Postgres lexes `app.route` as ONE token ('app.route'), not two.

    Verified against PG 16.14. If the query only produced 'app' | 'route' it would
    never match a document indexing the dotted lexeme -- and @app.route is one of
    the most distinctive identifiers in flask. Emit both forms so either matches.
    """
    assert tokenize("app.route(path)") == ["app.route", "app", "route", "path"]

def test_dotted_names_multi_segment():
    assert tokenize("self.app.config") == ["self.app.config", "self", "app", "config"]

def test_drops_single_characters():
    assert tokenize("how do I a b return") == ["how", "do", "return"]

def test_keeps_python_keywords():
    """'english' would strip these; they are Python keywords and must survive."""
    for kw in ("is", "not", "in", "and", "or", "if"):
        assert kw in tokenize(f"return {kw} something")

def test_deduplicates_preserving_order():
    assert tokenize("file file send file") == ["file", "send"]

def test_empty_text():
    assert tokenize("") == []


# --- tsquery construction ----------------------------------------------------

def test_ors_terms():
    assert build_tsquery("send_file") == "'send' | 'file'"

def test_ands_would_be_wrong():
    """A natural-language question ANDed against code matches nothing."""
    q = build_tsquery("how does url building work")
    assert "&" not in q and "|" in q

def test_includes_extra_terms():
    q = build_tsquery("url building", extra_terms=["url_for", "BuildError"])
    assert "'url'" in q and "'for'" in q and "'builderror'" in q

def test_extra_terms_are_deduplicated_against_question():
    q = build_tsquery("url", extra_terms=["url"])
    assert q.count("'url'") == 1

def test_rejects_quote_injection():
    """Tokens are filtered to alphanumerics, so a quote can never reach to_tsquery."""
    q = build_tsquery("foo' | bar'; DROP TABLE chunks --")
    assert "drop" in q  # kept as an ordinary lexeme
    assert ";" not in q and "--" not in q
    assert q.count("'") % 2 == 0

def test_empty_question_returns_none():
    assert build_tsquery("") is None

def test_only_stopwordy_short_tokens_returns_none():
    assert build_tsquery("a b c") is None
