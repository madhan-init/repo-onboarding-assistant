"""Lexical (keyword) arm of hybrid search.

Measured facts about Postgres 16.14 that shape this module:

  to_tsvector('simple','send_file')      -> 'file':2 'send':1    underscore splits FREE
  to_tsvector('simple','BuildError')     -> 'builderror':1       camelCase does NOT split
  to_tsvector('simple','app.route')      -> 'app.route':1        dotted names stay WHOLE
  to_tsvector('english','... if not authenticated')
                                         -> 'authent' 'respons' 'return'

So: the config must be 'simple' -- 'english' deletes `is`, `not`, `in`, `and`, `or`,
`if`, which are Python keywords -- and no identifier-splitting column is needed for
snake_case, which is most of Python. camelCase class names are the only identifiers
query expansion has to bridge.

Terms are OR-ed, not AND-ed. `plainto_tsquery` ANDs every term, so a natural-language
question would require a chunk to contain all of it and match essentially nothing;
ranking is left to ts_rank.
"""
import re
from typing import List, Optional

# Postgres keeps dotted names whole ('app.route'), so a query built only from the
# parts would miss them. Emit the dotted form *and* its components.
_DOTTED = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)+")
_TOKEN = re.compile(r"[a-z0-9]+")

MIN_TOKEN_LEN = 2


def tokenize(text: str) -> List[str]:
    """Lowercase, split like the 'simple' parser, drop 1-char noise, dedupe.

    Order: each dotted name, then its components, then remaining tokens.
    """
    lowered = (text or "").lower()
    seen, out = set(), []

    def add(token: str) -> None:
        if len(token) >= MIN_TOKEN_LEN and token not in seen:
            seen.add(token)
            out.append(token)

    for dotted in _DOTTED.findall(lowered):
        add(dotted)
        for part in _TOKEN.findall(dotted):
            add(part)
    for token in _TOKEN.findall(lowered):
        add(token)
    return out


def build_tsquery(question: str, extra_terms: Optional[List[str]] = None) -> Optional[str]:
    """Build an OR-ed to_tsquery string, or None when there is nothing to search.

    Tokens are filtered to `[a-z0-9.]+`, so no quote, semicolon or operator can
    reach to_tsquery regardless of what the question contained.
    """
    tokens = tokenize(question)
    seen = set(tokens)
    for term in extra_terms or []:
        for token in tokenize(term):
            if token not in seen:
                seen.add(token)
                tokens.append(token)
    if not tokens:
        return None
    return " | ".join(f"'{t}'" for t in tokens)
