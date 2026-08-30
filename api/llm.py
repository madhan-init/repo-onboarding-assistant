"""One place that builds the Anthropic client.

Identity-linked API keys (the kind an org/SSO setup issues) are rejected unless the
request carries an `anthropic-workspace-id` header naming the workspace it acts in:

    400 invalid_request_error: anthropic-workspace-id is required when
    authenticating with an identity-linked API key

The header is harmless on an ordinary key, so it is sent whenever
ANTHROPIC_WORKSPACE_ID is set and omitted otherwise. Both call sites go through
here so the two cannot drift.
"""
import os

import anthropic

MODEL = "claude-sonnet-4-6"


def get_client() -> anthropic.Anthropic:
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
    return anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        default_headers=headers,
    )
