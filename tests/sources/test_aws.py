import pytest

from collector.sources import aws
from tests.conftest import fixture_bytes
from tests.fakes import FakeHttp

FEED = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"


def test_keeps_only_ai_and_ml_announcements() -> None:
    http = FakeHttp({FEED: fixture_bytes("aws_whats_new_rss.xml")})

    items = aws.fetch(http)

    assert http.requested == [FEED]
    assert [item.title for item in items] == [
        "Amazon SageMaker HyperPod Inference Gateway for scalable LLM inference",
        "Run interactive workloads on Amazon EMR on EKS with Spark Connect",
        "Amazon Bedrock Managed Knowledge Base now supports Salesforce and Zendesk as native data source connectors",
        "Amazon CloudWatch Omni: AI-first observability for agents and applications",
        "OpenAI GPT-6 Sol and GPT-6 Luna are now generally available on Amazon Bedrock",
        "Claude Opus 5.5 is now available on AWS GovCloud (US)",
        "AWS HealthOmics now supports IAM session policies",
        "Amazon Connect Customer can now import evaluation form PDFs using AI",
        "Analyze your CloudTrail events using natural language in Amazon Q Console",
        "AWS Lambda durable functions integrates with Pydantic AI",
        "Amazon OpenSearch Serverless is now available on v0 by Vercel",
    ]


def test_descriptions_are_plain_text_and_short() -> None:
    items = aws.fetch(FakeHttp({FEED: fixture_bytes("aws_whats_new_rss.xml")}))

    assert all(0 < len(item.description) <= 200 for item in items)
    assert not any("<" in item.description for item in items)


@pytest.mark.parametrize(
    ("title", "tags", "expected"),
    [
        ("Amazon Bedrock adds a model", [], True),
        ("New SageMaker AI capability", [], True),
        ("Ask questions in Amazon Q Developer", [], True),
        ("Amazon Nova 2 Lite is available", [], True),
        ("Run LLMs on Graviton", [], True),
        ("Generative AI in your console", [], True),
        ("Machine learning inference is faster", [], True),
        ("Service X now supports ML-based detection", [], True),
        ("Claude model now available", ["general:products/amazon-bedrock"], True),
        ("HealthOmics update", ["marketing:marchitecture/artificial-intelligence"], True),
        ("Security Hub inventory", ["general:products/aiml"], True),
        ("JumpStart models", ["general:products/amazon-sagemaker-jumpstart"], True),
        # false positives the filter must avoid
        ("Amazon Quick adds Generate Sheet", [], False),
        ("Amazon QuickSight dashboards", ["general:products/amazon-quicksight"], False),
        (
            "Amazon Connect now enables agents to bid on shifts",
            ["general:products/amazon-connect"],
            False,
        ),
        ("HTML5 support in AppStream", [], False),
        ("Thai language support", [], False),
        ("Amazon Aurora adds MAIL notifications", [], False),
    ],
)
def test_is_ai_related(title: str, tags: list[str], expected: bool) -> None:
    assert aws.is_ai_related(title, tags) is expected


def test_every_item_is_on_the_sources_allowed_hosts() -> None:
    items = aws.fetch(FakeHttp({FEED: fixture_bytes("aws_whats_new_rss.xml")}))

    assert items
    assert all(aws.SOURCE.allows(item.url) for item in items)
