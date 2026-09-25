from collections.abc import Iterator
from datetime import UTC, datetime

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from collector.models import NewsItem
from collector.storage import DynamoRepository

TABLE = "ai-news-items"
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
ITEM = NewsItem(
    source="openai",
    title="Two years of OpenAI Academy",
    url="https://openai.com/index/two-years-of-openai-academy",
    published_at=datetime(2026, 9, 23, 16, 0, tzinfo=UTC),
    description="Marking two years of OpenAI Academy.",
)
SK = "2026-09-23T16:00:00Z#52e46e8371e1f69996c0f8fdcd7f1aabc16e63bd6bcc1139e79b18fa15fc40d2"
STORED_ATTRIBUTES = {
    "source": {"S": "openai"},
    "sk": {"S": SK},
    "title": {"S": "Two years of OpenAI Academy"},
    "url": {"S": "https://openai.com/index/two-years-of-openai-academy"},
    "publishedAt": {"S": "2026-09-23T16:00:00Z"},
    "description": {"S": "Marking two years of OpenAI Academy."},
    "fetchedAt": {"S": "2026-09-25T12:00:00Z"},
    "expiresAt": {"N": "1800705600"},  # 2026-09-25T12:00Z + 120 days = 2027-01-23T12:00Z
}


@pytest.fixture
def dynamodb() -> Iterator[tuple[DynamoRepository, Stubber]]:
    client = boto3.client(
        "dynamodb", region_name="eu-north-1", aws_access_key_id="test", aws_secret_access_key="test"
    )
    with Stubber(client) as stubber:
        yield DynamoRepository(client, TABLE), stubber
        stubber.assert_no_pending_responses()


def test_latest_is_a_newest_first_query_on_the_source_partition(
    dynamodb: tuple[DynamoRepository, Stubber],
) -> None:
    repo, stubber = dynamodb
    stubber.add_response(
        "query",
        {"Items": [STORED_ATTRIBUTES]},
        {
            "TableName": TABLE,
            "KeyConditionExpression": "#source = :source",
            "ExpressionAttributeNames": {"#source": "source"},
            "ExpressionAttributeValues": {":source": {"S": "openai"}},
            "ScanIndexForward": False,
            "Limit": 20,
        },
    )

    assert repo.latest("openai", 20) == [ITEM]


def test_put_new_writes_ttl_and_refuses_to_overwrite(
    dynamodb: tuple[DynamoRepository, Stubber],
) -> None:
    repo, stubber = dynamodb
    stubber.add_response(
        "put_item",
        {},
        {
            "TableName": TABLE,
            "Item": STORED_ATTRIBUTES,
            "ConditionExpression": "attribute_not_exists(#source)",
            "ExpressionAttributeNames": {"#source": "source"},
        },
    )

    assert repo.put_new(ITEM, NOW) is True


def test_put_new_reports_an_existing_item(dynamodb: tuple[DynamoRepository, Stubber]) -> None:
    repo, stubber = dynamodb
    stubber.add_client_error("put_item", service_error_code="ConditionalCheckFailedException")

    assert repo.put_new(ITEM, NOW) is False


def test_other_write_errors_propagate(dynamodb: tuple[DynamoRepository, Stubber]) -> None:
    repo, stubber = dynamodb
    stubber.add_client_error(
        "put_item", service_error_code="ProvisionedThroughputExceededException"
    )

    with pytest.raises(ClientError):
        repo.put_new(ITEM, NOW)
