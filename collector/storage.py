"""DynamoDB access. Reads are always a Query on one source partition: never a Scan.

Table "ai-news-items": PK `source` (e.g. "openai"), SK `sk` = "<publishedAt>#<sha256(url)>",
TTL attribute `expiresAt` (epoch seconds, first seen + 120 days).
"""

from datetime import datetime, timedelta
from typing import Any

from botocore.exceptions import ClientError

from collector.models import NewsItem, iso, parse_iso

TTL = timedelta(days=120)


class DynamoRepository:
    def __init__(self, client: Any, table: str) -> None:
        self._client = client  # a boto3 DynamoDB *client* (thread-safe, unlike resources)
        self._table = table

    def latest(self, source: str, limit: int) -> list[NewsItem]:
        response = self._client.query(
            TableName=self._table,
            KeyConditionExpression="#source = :source",
            ExpressionAttributeNames={"#source": "source"},
            ExpressionAttributeValues={":source": {"S": source}},
            ScanIndexForward=False,
            Limit=limit,
        )
        return [_from_attributes(raw) for raw in response.get("Items", [])]

    def put_new(self, item: NewsItem, now: datetime) -> bool:
        """Insert the item unless that exact key exists already. Returns True if written."""
        try:
            self._client.put_item(
                TableName=self._table,
                Item=_to_attributes(item, now),
                ConditionExpression="attribute_not_exists(#source)",
                ExpressionAttributeNames={"#source": "source"},
            )
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise
        return True


def _to_attributes(item: NewsItem, now: datetime) -> dict[str, dict[str, str]]:
    return {
        "source": {"S": item.source},
        "sk": {"S": item.sort_key},
        "title": {"S": item.title},
        "url": {"S": item.url},
        "publishedAt": {"S": iso(item.published_at)},
        "description": {"S": item.description},
        "fetchedAt": {"S": iso(now)},
        "expiresAt": {"N": str(int((now + TTL).timestamp()))},
    }


def _from_attributes(raw: dict[str, dict[str, str]]) -> NewsItem:
    return NewsItem(
        source=raw["source"]["S"],
        title=raw["title"]["S"],
        url=raw["url"]["S"],
        published_at=parse_iso(raw["publishedAt"]["S"]),
        description=raw.get("description", {}).get("S", ""),
    )
