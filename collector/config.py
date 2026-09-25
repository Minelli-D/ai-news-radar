"""Runtime settings. Everything AWS-specific comes from Lambda environment variables."""

import os

REPO_URL = os.environ.get("REPO_URL", "https://github.com/Minelli-D/ai-news-radar")
USER_AGENT = f"AINewsRadar/1.0 (+{REPO_URL})"

# How many of each source's newest items a run considers (and the per-source DynamoDB Query Limit).
ITEMS_PER_SOURCE = 20
