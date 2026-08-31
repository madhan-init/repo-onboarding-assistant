import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingester.metadata import classify_overview_error


def test_workspace_error_is_named_not_dumped():
    """The raw 404 JSON was being rendered to users as the repository overview."""
    raw = ("Error code: 404 - {'type': 'error', 'error': {'type': 'not_found_error', "
           "'message': 'Workspace `a1707b22-2861-469c-ab43-3861cc5d21dc` not found.'}}")
    msg = classify_overview_error(raw)
    assert "workspace" in msg.lower()
    assert "ANTHROPIC_WORKSPACE_ID" in msg
    assert "{" not in msg and "404 -" not in msg


def test_rate_limit_is_actionable():
    msg = classify_overview_error("Error code: 429 rate_limit_error exceeded")
    assert "rate limit" in msg.lower() and "re-index" in msg.lower()


def test_auth_error():
    msg = classify_overview_error("Error code: 401 authentication_error invalid x-api-key")
    assert "api key" in msg.lower()


def test_unknown_error_is_summarised_not_dumped():
    raw = "Error code: 500 - " + "x" * 5000
    msg = classify_overview_error(raw)
    assert len(msg) < 200
    assert "logs" in msg.lower()


def test_never_returns_empty():
    assert classify_overview_error("").strip()
