"""AWS Lambda entry point, invoked hourly by EventBridge Scheduler.

Environment: TABLE_NAME, BUCKET_NAME, SITE_URL (and optionally REPO_URL for the User-Agent).
The invocation fails (-> CloudWatch alarm) on infrastructure errors or when every source
failed; a single failing source is only reported in the log line and in news.json.
"""

import logging
import os
import time
from typing import Any

import boto3
from botocore.config import Config

from collector.config import USER_AGENT
from collector.http import HttpClient
from collector.models import utcnow
from collector.pipeline import run
from collector.publish import S3Publisher
from collector.sources import SOURCES
from collector.storage import DynamoRepository

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

SAFETY_MARGIN = 3.0  # seconds before the Lambda timeout that the run must be done by
# "adaptive" adds client-side rate limiting on throttling: the very first run inserts ~120 items
# into a table provisioned at 5 WCU. Whatever does not fit before the deadline is deferred.
_DYNAMODB_CONFIG = Config(
    retries={"mode": "adaptive", "max_attempts": 10}, connect_timeout=5, read_timeout=10
)
_S3_CONFIG = Config(
    retries={"mode": "standard", "max_attempts": 5}, connect_timeout=5, read_timeout=10
)


class CollectorError(RuntimeError):
    pass


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise CollectorError(f"missing environment variable {name}")
    return value


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    table = _required_env("TABLE_NAME")
    bucket = _required_env("BUCKET_NAME")
    site_url = _required_env("SITE_URL")
    remaining = context.get_remaining_time_in_millis() / 1000 if context else 60.0

    report = run(
        SOURCES,
        repo=DynamoRepository(boto3.client("dynamodb", config=_DYNAMODB_CONFIG), table),
        publisher=S3Publisher(boto3.client("s3", config=_S3_CONFIG), bucket),
        client_factory=lambda: HttpClient(USER_AGENT),
        site_url=site_url,
        now=utcnow(),
        deadline=time.monotonic() + remaining - SAFETY_MARGIN,
    )
    summary = report.summary()
    LOGGER.info("collector run finished", extra={"run": summary})
    if report.all_failed:
        raise CollectorError(f"every source failed: {summary['failed']}")
    return summary
